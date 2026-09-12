/**
 * Badge upload + render actions.
 *
 * Shared by HomePage and BadgeTray so validation rules exist in exactly one
 * place — v1's tray bypassed the uploader's type and size checks entirely.
 *
 * Both flows run with bounded concurrency and per-badge status, so a 20-photo
 * batch shows real progress, survives an individual failure, and can be
 * cancelled. v1 awaited each request in a bare `for` loop behind one boolean
 * spinner: no progress, no cancel, and one failure abandoned the rest.
 */

import { useCallback, useEffect, useRef } from 'react';

import { createSession, renderBadge, toApiError } from '../api/client';
import { useApp } from '../store/AppContext';
import { DEFAULT_CROP } from '../store/AppContext';
import type { BadgeItem } from '../store/types';

export const ALLOWED_TYPES = ['image/jpeg', 'image/png', 'image/webp'] as const;
export const MAX_FILE_MB = 20;
export const MAX_BATCH = 100;

/** How many requests may be in flight at once. */
const CONCURRENCY = 3;

export interface RejectedFile {
  name: string;
  reason: string;
}

export interface ValidationResult {
  accepted: File[];
  rejected: RejectedFile[];
}

export function validateFiles(files: ArrayLike<File>): ValidationResult {
  const accepted: File[] = [];
  const rejected: RejectedFile[] = [];

  for (let i = 0; i < files.length; i++) {
    const file = files[i];
    if (!file) continue;

    if (!ALLOWED_TYPES.includes(file.type as (typeof ALLOWED_TYPES)[number])) {
      rejected.push({ name: file.name, reason: 'not a JPEG, PNG or WebP' });
      continue;
    }
    if (file.size === 0) {
      rejected.push({ name: file.name, reason: 'the file is empty' });
      continue;
    }
    if (file.size > MAX_FILE_MB * 1024 * 1024) {
      rejected.push({
        name: file.name,
        reason: `${(file.size / 1024 / 1024).toFixed(1)} MB is over the ${MAX_FILE_MB} MB limit`,
      });
      continue;
    }
    if (accepted.length >= MAX_BATCH) {
      rejected.push({ name: file.name, reason: `over the ${MAX_BATCH}-photo batch limit` });
      continue;
    }
    accepted.push(file);
  }

  return { accepted, rejected };
}

export function describeRejections(rejected: RejectedFile[]): string {
  if (rejected.length === 0) return '';
  if (rejected.length === 1) {
    const only = rejected[0] as RejectedFile;
    return `Skipped "${only.name}" — ${only.reason}.`;
  }
  const head = rejected
    .slice(0, 3)
    .map((r) => `"${r.name}" (${r.reason})`)
    .join(', ');
  const more = rejected.length > 3 ? `, and ${rejected.length - 3} more` : '';
  return `Skipped ${rejected.length} files: ${head}${more}.`;
}

/** Run `worker` over `items` with at most `limit` in flight. Never rejects. */
async function mapWithConcurrency<T>(
  items: T[],
  limit: number,
  worker: (item: T, index: number) => Promise<void>,
): Promise<void> {
  let cursor = 0;
  const runners = Array.from({ length: Math.min(limit, items.length) }, async () => {
    while (cursor < items.length) {
      const index = cursor++;
      const item = items[index];
      if (item === undefined) continue;
      await worker(item, index);
    }
  });
  await Promise.all(runners);
}

function newBadgeId(index: number): string {
  const rand = Math.random().toString(36).slice(2, 8);
  return `badge-${Date.now().toString(36)}-${index}-${rand}`;
}

export function useBadgeActions() {
  const { state, dispatch } = useApp();
  const abortRef = useRef<AbortController | null>(null);

  // Cancel anything in flight if the component unmounts mid-batch.
  useEffect(() => {
    return () => abortRef.current?.abort();
  }, []);

  const cancel = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
    dispatch({ type: 'SET_BUSY', payload: false });
  }, [dispatch]);

  /**
   * Upload photos and add them to the tray.
   * Returns the badges that uploaded successfully.
   */
  const addPhotos = useCallback(
    async (files: ArrayLike<File>): Promise<BadgeItem[]> => {
      const { accepted, rejected } = validateFiles(files);

      if (rejected.length > 0) {
        dispatch({ type: 'SET_ERROR', payload: describeRejections(rejected) });
      } else {
        dispatch({ type: 'SET_ERROR', payload: null });
      }
      if (accepted.length === 0) return [];

      const controller = new AbortController();
      abortRef.current = controller;
      dispatch({ type: 'SET_BUSY', payload: true });

      // Placeholders appear immediately so the tray shows progress rather than
      // freezing until every upload finishes.
      const placeholders: BadgeItem[] = accepted.map((_, i) => ({
        id: newBadgeId(i),
        sessionId: '',
        photoUrl: '',
        photoW: 0,
        photoH: 0,
        templateId: state.selectedTemplateId,
        compositeUrl: null,
        copies: 1,
        crop: { ...DEFAULT_CROP },
        status: 'uploading',
        error: null,
        renderedDiameterMm: null,
        renderedBleedMm: null,
      }));
      dispatch({ type: 'ADD_BADGES', payload: placeholders });

      const succeeded: BadgeItem[] = [];
      const serverRejections: RejectedFile[] = [];

      await mapWithConcurrency(accepted, CONCURRENCY, async (file, index) => {
        const placeholder = placeholders[index];
        if (!placeholder) return;
        try {
          const session = await createSession(
            file,
            state.diameterMm,
            state.bleedMm,
            state.selectedTemplateId,
            controller.signal,
          );
          const changes: Partial<BadgeItem> = {
            sessionId: session.id,
            photoUrl: session.photo_url,
            photoW: session.photo_w,
            photoH: session.photo_h,
            status: 'idle',
            error: null,
          };
          dispatch({ type: 'UPDATE_BADGE', payload: { id: placeholder.id, changes } });
          succeeded.push({ ...placeholder, ...changes } as BadgeItem);
        } catch (err) {
          const apiErr = toApiError(err);
          if (apiErr.isCancel) {
            dispatch({ type: 'REMOVE_BADGE', payload: placeholder.id });
            return;
          }
          serverRejections.push({ name: file.name, reason: apiErr.message });
          dispatch({
            type: 'UPDATE_BADGE',
            payload: {
              id: placeholder.id,
              changes: { status: 'failed', error: apiErr.message },
            },
          });
        }
      });

      // The browser reports a file's type from its extension, so a text file
      // named ".png" passes client validation and only the server can catch
      // it. Those rejections must be summarised too, or the user is left with
      // a mystery "Failed" card and no reason.
      const allRejections = [...rejected, ...serverRejections];
      if (allRejections.length > 0) {
        dispatch({ type: 'SET_ERROR', payload: describeRejections(allRejections) });
      }

      dispatch({ type: 'SET_BUSY', payload: false });
      abortRef.current = null;
      return succeeded;
    },
    [dispatch, state.diameterMm, state.bleedMm, state.selectedTemplateId],
  );

  /** Render specific badges (or all of them) at the current geometry. */
  const renderBadges = useCallback(
    async (ids?: string[]): Promise<number> => {
      const targets = state.badges.filter(
        (b) => (ids ? ids.includes(b.id) : true) && b.sessionId && b.status !== 'uploading',
      );
      if (targets.length === 0) return 0;

      const controller = new AbortController();
      abortRef.current = controller;
      dispatch({ type: 'SET_BUSY', payload: true });
      dispatch({ type: 'SET_ERROR', payload: null });

      targets.forEach((b) =>
        dispatch({
          type: 'UPDATE_BADGE',
          payload: { id: b.id, changes: { status: 'rendering', error: null } },
        }),
      );

      let ok = 0;
      const failures: string[] = [];

      await mapWithConcurrency(targets, CONCURRENCY, async (badge) => {
        try {
          const result = await renderBadge(
            {
              session_id: badge.sessionId,
              template_id: badge.templateId ?? state.selectedTemplateId,
              diameter_mm: state.diameterMm,
              bleed_mm: state.bleedMm,
              crop: {
                offset_x: badge.crop.offsetX,
                offset_y: badge.crop.offsetY,
                scale: badge.crop.scale,
              },
            },
            controller.signal,
          );
          dispatch({
            type: 'UPDATE_BADGE',
            payload: {
              id: badge.id,
              changes: {
                compositeUrl: result.composite_url,
                status: 'ready',
                error: null,
                renderedDiameterMm: result.diameter_mm,
                renderedBleedMm: result.bleed_mm,
                // The server clamps the crop; adopt what it actually used so
                // the preview cannot drift from the render.
                crop: {
                  offsetX: result.crop.offset_x,
                  offsetY: result.crop.offset_y,
                  scale: result.crop.scale,
                },
              },
            },
          });
          ok += 1;
        } catch (err) {
          const apiErr = toApiError(err);
          if (apiErr.isCancel) {
            dispatch({
              type: 'UPDATE_BADGE',
              payload: { id: badge.id, changes: { status: 'idle' } },
            });
            return;
          }
          failures.push(apiErr.message);
          dispatch({
            type: 'UPDATE_BADGE',
            payload: { id: badge.id, changes: { status: 'failed', error: apiErr.message } },
          });
        }
      });

      if (failures.length > 0) {
        const unique = Array.from(new Set(failures));
        dispatch({
          type: 'SET_ERROR',
          payload:
            failures.length === targets.length
              ? unique[0] ?? 'Rendering failed.'
              : `${failures.length} of ${targets.length} badges failed to render. ${unique[0] ?? ''}`,
        });
      }

      dispatch({ type: 'SET_BUSY', payload: false });
      abortRef.current = null;
      return ok;
    },
    [dispatch, state.badges, state.diameterMm, state.bleedMm, state.selectedTemplateId],
  );

  return { addPhotos, renderBadges, cancel };
}
