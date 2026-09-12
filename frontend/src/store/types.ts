// ─────────────────────────────────────────────────────────────────
//  Shared application types.
//  Types only — no runtime values. Import with `import type`.
// ─────────────────────────────────────────────────────────────────

import type { Orientation, PaperSize } from '../utils/paperLayouts';

export type { Orientation, PaperSize };
export type AppStep = 'input' | 'editor' | 'print';

/** Lifecycle of one badge in the tray. Drives per-item UI, not a global spinner. */
export type BadgeStatus = 'uploading' | 'idle' | 'rendering' | 'ready' | 'failed';

export interface PrintConfig {
  paper: PaperSize;
  orientation: Orientation;
  copies: number | 'auto';
  gapMm: number;
  marginMm: number;
  includeRuler: boolean;
  drawGuides: boolean;
  /**
   * Extra DIAMETER beyond the badge for the cutter / perforation ring, in mm.
   * Badge presses need a paper disc wider than the trim so the rim folds
   * around the shell; the allowance differs per machine. 0 disables the ring.
   */
  perforationMm: number;
}

export interface BadgeTemplate {
  id: string;
  name: string;
  category: string;
  thumbnail_url: string;
  full_url: string;
  width: number;
  height: number;
  is_square: boolean;
}

/**
 * Crop state.
 *
 * offsetX/offsetY are NORMALISED — fractions of the badge's total diameter,
 * not pixels. That keeps the preview and the 300 DPI render in agreement no
 * matter how large the preview is drawn, and survives responsive layouts and
 * browser zoom. scale is a multiplier on cover-fit; 1.0 exactly fills the
 * circle, and anything less would expose background.
 */
export interface CropState {
  offsetX: number;
  offsetY: number;
  scale: number;
}

export interface BadgeItem {
  id: string;
  sessionId: string;
  /** Server URL. Photos are NOT kept as data URLs — a batch of them exhausts memory. */
  photoUrl: string;
  photoW: number;
  photoH: number;
  templateId: string | null;
  compositeUrl: string | null;
  copies: number;
  crop: CropState;
  status: BadgeStatus;
  error: string | null;
  /** Geometry the current composite was actually rendered at. */
  renderedDiameterMm: number | null;
  renderedBleedMm: number | null;
}

export interface AppState {
  step: AppStep;
  diameterMm: number;
  bleedMm: number;
  selectedTemplateId: string | null;
  printConfig: PrintConfig;
  badges: BadgeItem[];
  activeBadgeId: string | null;
  isBusy: boolean;
  error: string | null;
  /** Bumped whenever state has been restored from storage, to re-sync children. */
  hydrated: boolean;
}

export type AppAction =
  | { type: 'SET_STEP'; payload: AppStep }
  | { type: 'SET_DIAMETER'; payload: number }
  | { type: 'SET_BLEED'; payload: number }
  | { type: 'SET_TEMPLATE'; payload: string | null }
  | { type: 'APPLY_TEMPLATE_TO_ALL'; payload: string | null }
  | { type: 'SET_PRINT_CONFIG'; payload: Partial<PrintConfig> }
  | { type: 'ADD_BADGES'; payload: BadgeItem[] }
  | { type: 'UPDATE_BADGE'; payload: { id: string; changes: Partial<BadgeItem> } }
  | { type: 'REMOVE_BADGE'; payload: string }
  | { type: 'SET_ACTIVE_BADGE'; payload: string }
  | { type: 'SET_CROP'; payload: { id: string; crop: CropState } }
  | { type: 'SET_BUSY'; payload: boolean }
  | { type: 'SET_ERROR'; payload: string | null }
  | { type: 'HYDRATE'; payload: Partial<AppState> }
  | { type: 'RESET' };

/**
 * A badge is stale when its composite was rendered at geometry that no longer
 * matches the current settings. Printing a stale badge would put a different
 * physical size on paper than the UI promises, so the app must never do it
 * silently.
 */
export function isStale(badge: BadgeItem, diameterMm: number, bleedMm: number): boolean {
  if (!badge.compositeUrl) return true;
  if (badge.renderedDiameterMm === null || badge.renderedBleedMm === null) return true;
  return (
    Math.abs(badge.renderedDiameterMm - diameterMm) > 0.001 ||
    Math.abs(badge.renderedBleedMm - bleedMm) > 0.001
  );
}

export function isPrintable(badge: BadgeItem, diameterMm: number, bleedMm: number): boolean {
  return badge.status === 'ready' && !isStale(badge, diameterMm, bleedMm);
}
