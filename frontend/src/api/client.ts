/**
 * Typed API client.
 *
 * Every response has a declared shape, so a backend field rename fails the
 * build instead of surfacing as `undefined` at runtime. Errors are normalised
 * to a single readable sentence — the backend already returns actionable
 * `detail` strings, and those should reach the user verbatim.
 */

import axios, { AxiosError } from 'axios';

export const API_BASE: string =
  (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? '';

export const api = axios.create({
  baseURL: API_BASE,
  // Rendering a large batch is genuinely slow; per-request overrides below.
  timeout: 60_000,
});

// ─────────────────────────────────────────────────────────────────
//  Response shapes (mirror the backend pydantic models)
// ─────────────────────────────────────────────────────────────────

export interface TemplateDto {
  id: string;
  name: string;
  category: string;
  thumbnail_url: string;
  full_url: string;
  width: number;
  height: number;
  is_square: boolean;
}

export interface SessionDto {
  id: string;
  photo_url: string;
  composite_url: string | null;
  template_id: string | null;
  diameter_mm: number;
  bleed_mm: number;
  crop: { offset_x: number; offset_y: number; scale: number };
  photo_w: number;
  photo_h: number;
  render_version: number;
}

export interface RenderDto {
  session_id: string;
  composite_url: string;
  badge_px: number;
  bleed_px: number;
  total_px: number;
  diameter_mm: number;
  bleed_mm: number;
  total_diameter_mm: number;
  dpi: number;
  render_version: number;
  crop: { offset_x: number; offset_y: number; scale: number };
}

export interface LayoutDto {
  paper: string;
  orientation: string;
  fits: boolean;
  reason: string;
  cols: number;
  rows: number;
  capacity_per_page: number;
  requested: number;
  total_badges: number;
  pages: number;
  paper_mm: { w: number; h: number };
  origin_mm: { x: number; y: number };
  step_mm: number;
}

export interface ExportDto {
  urls: string[];
  /** Attachment endpoints; the server sets the filename via Content-Disposition. */
  download_urls: string[];
  total_pages: number;
  badges_placed: number;
  truncated: boolean;
  layout: LayoutDto;
  diameter_mm: number;
  bleed_mm: number;
}

export interface ExportPayload {
  session_id?: string;
  items?: { session_id: string; copies: number }[];
  paper: string;
  orientation: string;
  copies?: number | null;
  gap_mm: number;
  margin_mm: number;
  include_ruler: boolean;
  draw_guides: boolean;
  perforation_mm: number;
  expect_diameter_mm?: number;
}

// ─────────────────────────────────────────────────────────────────
//  Errors
// ─────────────────────────────────────────────────────────────────

export class ApiError extends Error {
  readonly status: number | null;
  readonly isCancel: boolean;

  constructor(message: string, status: number | null, isCancel = false) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.isCancel = isCancel;
  }
}

/** Turn anything thrown by axios into one sentence worth showing a user. */
export function toApiError(err: unknown): ApiError {
  if (err instanceof ApiError) return err;

  if (axios.isCancel(err)) {
    return new ApiError('Cancelled.', null, true);
  }

  if (axios.isAxiosError(err)) {
    const ax = err as AxiosError<{ detail?: string }>;

    if (ax.code === 'ECONNABORTED') {
      return new ApiError('That took too long and timed out. Please try again.', null);
    }
    if (!ax.response) {
      return new ApiError(
        'Cannot reach the Button Buddy server. Check that the backend is running.',
        null,
      );
    }
    const detail = ax.response.data?.detail;
    if (typeof detail === 'string' && detail.trim()) {
      return new ApiError(detail, ax.response.status);
    }
    return new ApiError(
      `The server returned an error (${ax.response.status}).`,
      ax.response.status,
    );
  }

  return new ApiError(err instanceof Error ? err.message : 'Something went wrong.', null);
}

async function call<T>(fn: () => Promise<{ data: T }>): Promise<T> {
  try {
    const { data } = await fn();
    return data;
  } catch (err) {
    throw toApiError(err);
  }
}

/** Absolute URL for a path the API returned. */
export function assetUrl(path: string): string {
  if (!path) return '';
  if (/^https?:\/\//i.test(path)) return path;
  return `${API_BASE}${path.startsWith('/') ? '' : '/'}${path}`;
}

/**
 * Download a file to disk.
 *
 * Not `<a href download target="_blank">`: browsers IGNORE the `download`
 * attribute when `target="_blank"` is also present, and open the PDF in a new
 * tab's built-in viewer instead — which a popup blocker can then suppress
 * entirely, so the click appears to do nothing at all.
 *
 * Fetching the bytes and clicking a synthetic anchor is immune to both, and
 * lets us give the file a meaningful name rather than `sheet_4x6_portrait.pdf`.
 */
export async function downloadFile(url: string, filename: string): Promise<void> {
  const response = await fetch(assetUrl(url), { credentials: 'omit' });
  if (!response.ok) {
    throw new ApiError(
      `Could not fetch the file to download (${response.status}).`,
      response.status,
    );
  }
  const blob = await response.blob();
  const objectUrl = URL.createObjectURL(blob);
  try {
    const a = document.createElement('a');
    a.href = objectUrl;
    a.download = filename;
    a.rel = 'noopener';
    document.body.appendChild(a);
    a.click();
    a.remove();
  } finally {
    // Revoke on the next tick: revoking synchronously can cancel the download
    // in some browsers before it has started reading the blob.
    window.setTimeout(() => URL.revokeObjectURL(objectUrl), 10_000);
  }
}

/**
 * Start a download from a URL the SERVER marks as an attachment.
 *
 * The most reliable mechanism available: when the response carries
 * `Content-Disposition: attachment; filename=...`, the browser must save it
 * under that name. No client-side attribute is involved, so nothing — popup
 * blockers, `target` handling, or enterprise download policy — can rename it
 * to a UUID or strip its extension.
 *
 * A hidden iframe is used rather than `location.href` so the current page is
 * never even momentarily navigated away from.
 */
export function triggerBrowserDownload(url: string): void {
  const frame = document.createElement('iframe');
  frame.style.display = 'none';
  frame.src = url;
  document.body.appendChild(frame);
  window.setTimeout(() => frame.remove(), 60_000);
}

// ─────────────────────────────────────────────────────────────────
//  Endpoints
// ─────────────────────────────────────────────────────────────────

export function fetchTemplates(signal?: AbortSignal): Promise<TemplateDto[]> {
  return call(() => api.get<TemplateDto[]>('/api/templates', { signal }));
}

export function fetchSession(sessionId: string, signal?: AbortSignal): Promise<SessionDto> {
  return call(() => api.get<SessionDto>(`/api/sessions/${sessionId}`, { signal }));
}

export function createSession(
  photo: File,
  diameterMm: number,
  bleedMm: number,
  templateId?: string | null,
  signal?: AbortSignal,
  onProgress?: (fraction: number) => void,
): Promise<SessionDto> {
  const form = new FormData();
  form.append('photo', photo);
  form.append('diameter_mm', String(diameterMm));
  form.append('bleed_mm', String(bleedMm));
  if (templateId) form.append('template_id', templateId);

  return call(() =>
    api.post<SessionDto>('/api/sessions', form, {
      signal,
      timeout: 120_000,
      onUploadProgress: (e) => {
        if (onProgress && e.total) onProgress(e.loaded / e.total);
      },
    }),
  );
}

export function deleteSession(sessionId: string): Promise<void> {
  return call(() => api.delete(`/api/sessions/${sessionId}`)).then(() => undefined);
}

export interface RenderPayload {
  session_id: string;
  template_id: string | null;
  diameter_mm: number;
  bleed_mm: number;
  crop: { offset_x: number; offset_y: number; scale: number };
}

export function renderBadge(payload: RenderPayload, signal?: AbortSignal): Promise<RenderDto> {
  return call(() => api.post<RenderDto>('/api/render', payload, { signal, timeout: 120_000 }));
}

export function exportPngSheet(payload: ExportPayload, signal?: AbortSignal): Promise<ExportDto> {
  return call(() =>
    api.post<ExportDto>('/api/export/png-sheet', payload, { signal, timeout: 180_000 }),
  );
}

export function exportPdf(payload: ExportPayload, signal?: AbortSignal): Promise<ExportDto> {
  return call(() =>
    api.post<ExportDto>('/api/export/pdf', payload, { signal, timeout: 180_000 }),
  );
}

export interface LayoutQuery {
  paper: string;
  orientation: string;
  diameter_mm: number;
  bleed_mm: number;
  gap_mm: number;
  margin_mm: number;
  copies?: number | null;
  include_ruler: boolean;
}

export function previewLayout(q: LayoutQuery, signal?: AbortSignal): Promise<LayoutDto> {
  return call(() => api.post<LayoutDto>('/api/layout', q, { signal }));
}

export interface HealthDto {
  status: string;
  database: boolean;
  uploads_writable: boolean;
  print_dpi: number;
}

export function fetchHealth(signal?: AbortSignal): Promise<HealthDto> {
  return call(() => api.get<HealthDto>('/api/health', { signal, timeout: 5_000 }));
}
