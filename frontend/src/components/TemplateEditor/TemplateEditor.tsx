/**
 * Badge editor — the WYSIWYG surface.
 *
 * GEOMETRY CONTRACT (mirrors backend/app/services/compositor.py)
 * -------------------------------------------------------------
 * The preview box represents the *total* badge footprint (trim + 2 × bleed).
 * The photo is `object-fit: cover` inside it, then transformed by
 *
 *     translate(offsetX * box, offsetY * box) scale(scale)
 *
 * with `transform-origin: center`. The backend cover-fits to `total_px` and
 * pastes at `(total - scaled)/2 + offset * total`, which is the same
 * operation at 300 DPI. Because offsets are fractions of the box, the preview
 * can be any size on screen — responsive, zoomed, high-DPI — and the render
 * still matches. v1 sent raw CSS pixels and assumed a 96 DPI box.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import './TemplateEditor.css';
import { assetUrl } from '../../api/client';
import { useApp } from '../../store/AppContext';
import { useBadgeActions } from '../../hooks/useBadgeActions';
import { isStale } from '../../store/types';
import type { BadgeTemplate, CropState } from '../../store/types';
import { mmToPx } from '../../utils/mmToPx';

/** Largest on-screen preview, in CSS px. Purely cosmetic — geometry is normalised. */
const MAX_PREVIEW_PX = 460;
const MIN_PREVIEW_PX = 200;
const MIN_SCALE = 1.0;
const MAX_SCALE = 8.0;

interface Props {
  templates: BadgeTemplate[];
}

/**
 * Largest offset that keeps the photo covering the circle. Panning past this
 * would expose background as a sliver inside the badge — never intended.
 * Mirrors `clamp_offsets` in the compositor.
 */
function clampCrop(crop: CropState, photoW: number, photoH: number): CropState {
  const scale = Math.min(MAX_SCALE, Math.max(MIN_SCALE, crop.scale));
  if (photoW <= 0 || photoH <= 0) {
    return { offsetX: 0, offsetY: 0, scale };
  }
  const longOverShort = Math.max(photoW, photoH) / Math.min(photoW, photoH);
  const extentX = scale * (photoW >= photoH ? longOverShort : 1);
  const extentY = scale * (photoH > photoW ? longOverShort : 1);
  const maxX = Math.max(0, (extentX - 1) / 2);
  const maxY = Math.max(0, (extentY - 1) / 2);
  return {
    offsetX: Math.max(-maxX, Math.min(maxX, crop.offsetX)),
    offsetY: Math.max(-maxY, Math.min(maxY, crop.offsetY)),
    scale,
  };
}

export function TemplateEditor({ templates }: Props) {
  const { state, dispatch, activeBadge } = useApp();
  const { diameterMm, bleedMm, badges, isBusy } = state;
  const { renderBadges } = useBadgeActions();

  const boxRef = useRef<HTMLDivElement>(null);
  const dragRef = useRef<{ x: number; y: number; pointerId: number } | null>(null);
  const [localCrop, setLocalCrop] = useState<CropState>(
    activeBadge?.crop ?? { offsetX: 0, offsetY: 0, scale: 1 },
  );
  const cropRef = useRef<CropState>(localCrop);

  /*
   * Re-sync from the store ONLY when the selected badge changes.
   *
   * Depending on `activeBadge.crop` as well would make this fight the editor:
   * every commit produces a new crop object, which would push a value back
   * into local state mid-gesture and fight the user's drag.
   */
  const syncedIdRef = useRef<string | null>(null);
  useEffect(() => {
    const id = activeBadge?.id ?? null;
    if (syncedIdRef.current === id) return;
    syncedIdRef.current = id;
    const next = activeBadge?.crop ?? { offsetX: 0, offsetY: 0, scale: 1 };
    cropRef.current = next;
    setLocalCrop(next);
  }, [activeBadge?.id, activeBadge?.crop, activeBadge]);

  const totalMm = diameterMm + bleedMm * 2;

  // Preview size is free to be anything; it only scales the *display*.
  const boxPx = useMemo(() => {
    const cssPx = Math.round(totalMm * 3.779528); // 1 mm at nominal 96 DPI
    return Math.max(MIN_PREVIEW_PX, Math.min(MAX_PREVIEW_PX, cssPx));
  }, [totalMm]);

  const bleedFraction = totalMm > 0 ? bleedMm / totalMm : 0;
  const trimInsetPx = bleedFraction * boxPx;

  const activeTemplate = templates.find((t) => t.id === activeBadge?.templateId) ?? null;
  const stale = activeBadge ? isStale(activeBadge, diameterMm, bleedMm) : false;

  /**
   * The live crop is mirrored into a ref.
   *
   * A pan is a burst of functional `setLocalCrop` updates, so by the time
   * `pointerup` fires the handler's closure still holds the crop from whatever
   * render it was created in — committing that would overwrite the store with
   * a pre-drag value and snap the photo back. The ref always holds the value
   * the user actually dragged to.
   */
  const applyCrop = useCallback(
    (update: (c: CropState) => CropState) => {
      if (!activeBadge) return;
      setLocalCrop((current) => {
        const next = clampCrop(update(current), activeBadge.photoW, activeBadge.photoH);
        cropRef.current = next;
        return next;
      });
    },
    [activeBadge],
  );

  const pushCrop = useCallback(() => {
    if (!activeBadge) return;
    dispatch({ type: 'SET_CROP', payload: { id: activeBadge.id, crop: cropRef.current } });
  }, [activeBadge, dispatch]);

  const commitCrop = useCallback(
    (next: CropState) => {
      applyCrop(() => next);
      // Read back through the ref on the next tick so we persist the clamped
      // value, not the requested one.
      window.setTimeout(pushCrop, 0);
    },
    [applyCrop, pushCrop],
  );

  // ---- Pan --------------------------------------------------------------
  const onPointerDown = (e: React.PointerEvent<HTMLDivElement>) => {
    if (!activeBadge) return;
    e.currentTarget.setPointerCapture(e.pointerId);
    dragRef.current = { x: e.clientX, y: e.clientY, pointerId: e.pointerId };
  };

  const onPointerMove = (e: React.PointerEvent<HTMLDivElement>) => {
    const drag = dragRef.current;
    if (!drag || !activeBadge) return;
    const size = boxRef.current?.getBoundingClientRect().width || boxPx;
    // A pixel drag becomes a fraction of the badge diameter — the unit the
    // render API speaks, and the reason preview size does not matter.
    const dx = (e.clientX - drag.x) / size;
    const dy = (e.clientY - drag.y) / size;
    dragRef.current = { ...drag, x: e.clientX, y: e.clientY };
    applyCrop((c) => ({ ...c, offsetX: c.offsetX + dx, offsetY: c.offsetY + dy }));
  };

  const endDrag = (e: React.PointerEvent<HTMLDivElement>) => {
    const drag = dragRef.current;
    if (!drag) return;
    e.currentTarget.releasePointerCapture?.(drag.pointerId);
    dragRef.current = null;
    pushCrop();
  };

  // ---- Zoom -------------------------------------------------------------
  // Non-passive listener: React's onWheel is passive, so preventDefault()
  // there is ignored and the page scrolls while you zoom.
  useEffect(() => {
    const el = boxRef.current;
    if (!el || !activeBadge) return;

    let settle: number | undefined;
    const onWheel = (e: WheelEvent) => {
      e.preventDefault();
      const factor = e.deltaY > 0 ? 0.94 : 1.06;
      applyCrop((c) => ({
        ...c,
        scale: Math.min(MAX_SCALE, Math.max(MIN_SCALE, c.scale * factor)),
      }));
      // Persist once the wheel stops, not on every tick.
      window.clearTimeout(settle);
      settle = window.setTimeout(pushCrop, 200);
    };

    el.addEventListener('wheel', onWheel, { passive: false });
    return () => {
      window.clearTimeout(settle);
      el.removeEventListener('wheel', onWheel);
    };
  }, [activeBadge, applyCrop, pushCrop]);

  // ---- Keyboard nudge (accessibility + precision) ------------------------
  const onKeyDown = (e: React.KeyboardEvent<HTMLDivElement>) => {
    if (!activeBadge) return;
    const step = e.shiftKey ? 0.05 : 0.01;
    const map: Record<string, [number, number]> = {
      ArrowLeft: [-step, 0],
      ArrowRight: [step, 0],
      ArrowUp: [0, -step],
      ArrowDown: [0, step],
    };
    const delta = map[e.key];
    if (delta) {
      e.preventDefault();
      commitCrop({ ...localCrop, offsetX: localCrop.offsetX + delta[0], offsetY: localCrop.offsetY + delta[1] });
      return;
    }
    if (e.key === '+' || e.key === '=') {
      e.preventDefault();
      commitCrop({ ...localCrop, scale: localCrop.scale * 1.1 });
    } else if (e.key === '-' || e.key === '_') {
      e.preventDefault();
      commitCrop({ ...localCrop, scale: localCrop.scale / 1.1 });
    }
  };

  if (!activeBadge) {
    return (
      <div className="te-empty card">
        <div className="drop-icon">🖼️</div>
        <h3>No badge selected</h3>
        <p>Add a photo to the tray above, then select it here to frame and render it.</p>
      </div>
    );
  }

  const badgeIndex = badges.findIndex((b) => b.id === activeBadge.id);
  const label = badgeIndex >= 0 ? `Badge ${badgeIndex + 1}` : 'Badge';
  const canPanX = clampCrop({ ...localCrop, offsetX: 999 }, activeBadge.photoW, activeBadge.photoH).offsetX > 0;
  const canPanY = clampCrop({ ...localCrop, offsetY: 999 }, activeBadge.photoW, activeBadge.photoH).offsetY > 0;
  const canPan = canPanX || canPanY;

  return (
    <div className="template-editor">
      <div className="te-preview-wrap">
        <div
          ref={boxRef}
          className={`te-canvas-area ${canPan ? 'can-pan' : ''}`}
          style={{ width: `${boxPx}px`, height: `${boxPx}px` }}
          onPointerDown={onPointerDown}
          onPointerMove={onPointerMove}
          onPointerUp={endDrag}
          onPointerCancel={endDrag}
          onKeyDown={onKeyDown}
          role="application"
          tabIndex={0}
          aria-label={`${label} framing. Drag to pan, scroll to zoom, arrow keys to nudge.`}
          title={canPan ? 'Drag to reposition · Scroll to zoom' : 'Zoom in to reposition'}
        >
          {activeBadge.photoUrl && (
            <img
              src={assetUrl(activeBadge.photoUrl)}
              className="te-photo-layer"
              style={{
                transform:
                  `translate(${localCrop.offsetX * 100}%, ${localCrop.offsetY * 100}%) ` +
                  `scale(${localCrop.scale})`,
              }}
              alt=""
              draggable={false}
            />
          )}

          {activeTemplate && (
            <img
              src={assetUrl(activeTemplate.full_url)}
              className="te-template-layer"
              alt=""
              draggable={false}
            />
          )}

          {/* Trim line: where the badge press actually cuts. Only meaningful
              when there is bleed, otherwise it IS the artwork edge. */}
          {bleedMm > 0 && (
            <div
              className="te-trim-ring"
              style={{ inset: `${trimInsetPx}px` }}
              aria-hidden="true"
            />
          )}
        </div>

        <div className="te-size-caption">
          <strong>{diameterMm.toFixed(1)} mm</strong> badge
          {bleedMm > 0 && <> · {bleedMm.toFixed(1)} mm bleed → {totalMm.toFixed(1)} mm artwork</>}
          <span className="te-dim"> · {mmToPx(totalMm)} px @ 300 DPI</span>
        </div>
      </div>

      <div className="te-controls">
        <div className="te-zoom-row">
          <label className="label" htmlFor="te-zoom">Zoom</label>
          <input
            id="te-zoom"
            type="range"
            className="range-slider"
            min={MIN_SCALE}
            max={4}
            step={0.01}
            value={localCrop.scale}
            onChange={(e) =>
              commitCrop({ ...localCrop, scale: parseFloat(e.target.value) })
            }
          />
          <span className="te-zoom-val">{localCrop.scale.toFixed(2)}×</span>
        </div>

        <div className="te-actions">
          <button
            type="button"
            className="btn btn-ghost btn-sm"
            onClick={() => commitCrop({ offsetX: 0, offsetY: 0, scale: 1 })}
            disabled={localCrop.scale === 1 && localCrop.offsetX === 0 && localCrop.offsetY === 0}
          >
            ↺ Reset framing
          </button>

          <button
            id="btn-render"
            type="button"
            className={`btn ${stale ? 'btn-primary' : 'btn-secondary'}`}
            onClick={() => void renderBadges([activeBadge.id])}
            disabled={isBusy || activeBadge.status === 'uploading'}
          >
            {activeBadge.status === 'rendering' ? (
              <><span className="spinner" /> Rendering…</>
            ) : (
              `✦ Render ${label}`
            )}
          </button>

          {badges.length > 1 && (
            <button
              id="btn-render-all"
              type="button"
              className="btn btn-primary"
              onClick={() => void renderBadges()}
              disabled={isBusy}
            >
              ✦ Render all {badges.length}
            </button>
          )}
        </div>
      </div>

      {activeBadge.error && (
        <div className="error-banner" role="alert">⚠️ {activeBadge.error}</div>
      )}

      {activeBadge.compositeUrl && (
        <div className="te-result">
          <div className="te-result-head">
            <span className="label">Rendered result</span>
            {stale ? (
              <span className="badge badge-warn">
                Out of date — rendered at {activeBadge.renderedDiameterMm?.toFixed(1)} mm
              </span>
            ) : (
              <span className="badge badge-success">
                ✓ {activeBadge.renderedDiameterMm?.toFixed(1)} mm · print ready
              </span>
            )}
          </div>
          <img
            src={assetUrl(activeBadge.compositeUrl)}
            alt={`${label} rendered at ${activeBadge.renderedDiameterMm ?? diameterMm} mm`}
            className={`te-result-img ${stale ? 'is-stale' : ''}`}
            style={{ width: `${boxPx}px`, height: `${boxPx}px` }}
          />
          {stale && (
            <p className="te-stale-note">
              You changed the size after rendering. Render again so the printed badge is
              exactly {diameterMm.toFixed(1)} mm.
            </p>
          )}
        </div>
      )}
    </div>
  );
}
