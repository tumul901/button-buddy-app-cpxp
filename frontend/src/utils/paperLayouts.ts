/**
 * Sheet layout — mirror of backend/app/services/layout.py.
 *
 * This exists so sliders give instant feedback without a round trip. The
 * backend is the authority; the two are kept identical by a parity test
 * (backend/tests/test_layout.py::test_frontend_layout_matches_backend) that
 * actually executes this file under node and compares every result.
 *
 * CAPACITY
 * --------
 * N badges in a row occupy N*d + (N-1)*gap — the last one has no gap after it:
 *
 *     N = floor((usable + gap) / (d + gap))
 *
 * The naive floor(usable / (d + gap)) charges a trailing gap to the last badge
 * and undercounts. On US Letter at 58 mm with a 10 mm gap it reports 6 where 9
 * actually fit — a third of the sheet thrown away.
 */

export type PaperSize = 'A4' | 'A3' | 'Letter' | 'Legal' | '4x6';
export type Orientation = 'portrait' | 'landscape';

export const PAPER_SIZES_MM: Record<PaperSize, { w: number; h: number }> = {
  A4: { w: 210.0, h: 297.0 },
  A3: { w: 297.0, h: 420.0 },
  Letter: { w: 215.9, h: 279.4 },
  Legal: { w: 215.9, h: 355.6 },
  '4x6': { w: 101.6, h: 152.4 },
};

export const PAPER_LABELS: Record<PaperSize, string> = {
  A4: 'A4 · 210 × 297 mm',
  A3: 'A3 · 297 × 420 mm',
  Letter: 'Letter · 8.5 × 11 in',
  Legal: 'Legal · 8.5 × 14 in',
  '4x6': '4 × 6 in photo · 102 × 152 mm',
};

/** Band reserved at the top of the sheet for the calibration ruler. */
export const RULER_BAND_MM = 12.0;

export interface SheetLayout {
  paper: PaperSize;
  orientation: Orientation;
  fits: boolean;
  reason: string;
  cols: number;
  rows: number;
  capacityPerPage: number;
  requested: number;
  totalBadges: number;
  pages: number;
  paperMm: { w: number; h: number };
  badgeDiameterMm: number;
  gapMm: number;
  marginMm: number;
  reserveTopMm: number;
  originMm: { x: number; y: number };
  stepMm: number;
}

/**
 * The layout cell for one badge.
 *
 * It must hold whichever is larger: the printed artwork (trim + 2 x bleed) or
 * the cutter ring (trim + perforation). Sizing to the artwork alone would let
 * adjacent perforation circles overlap and run off the page.
 */
export function cellSizeMm(diameterMm: number, bleedMm: number, perforationMm: number): number {
  return Math.max(diameterMm + bleedMm * 2, diameterMm + perforationMm);
}

/** How many `sizeMm` items fit in `usableMm` with `gapMm` between them. */
export function fitCount(usableMm: number, sizeMm: number, gapMm: number): number {
  if (sizeMm <= 0 || usableMm < sizeMm) return 0;
  return Math.floor((usableMm + gapMm + 1e-9) / (sizeMm + gapMm));
}

/**
 * @param diameterMm  Effective badge footprint, i.e. trim diameter + 2 × bleed.
 * @param copies      undefined means "fill the page".
 * @param reserveTopMm Band at the top that badges must not enter.
 */
export function computeLayout(
  paper: PaperSize,
  orientation: Orientation,
  diameterMm: number,
  gapMm: number,
  marginMm: number,
  copies?: number,
  reserveTopMm: number = RULER_BAND_MM,
): SheetLayout {
  let { w, h } = PAPER_SIZES_MM[paper];
  if (orientation === 'landscape') {
    [w, h] = [h, w];
  }

  const usableW = w - marginMm * 2;
  const usableH = h - marginMm * 2 - reserveTopMm;

  const cols = fitCount(usableW, diameterMm, gapMm);
  const rows = fitCount(usableH, diameterMm, gapMm);
  const capacityPerPage = cols * rows;
  const fits = capacityPerPage > 0;

  let reason = '';
  if (!fits) {
    if (usableW < diameterMm) {
      reason =
        `A ${diameterMm.toFixed(1)} mm badge does not fit across ${paper} ${orientation} ` +
        `(${w.toFixed(1)} mm) with ${marginMm.toFixed(1)} mm margins. ` +
        `Reduce the diameter or the margin.`;
    } else {
      reason =
        `A ${diameterMm.toFixed(1)} mm badge does not fit down ${paper} ${orientation} ` +
        `(${h.toFixed(1)} mm) with ${marginMm.toFixed(1)} mm margins` +
        (reserveTopMm ? ` and a ${reserveTopMm.toFixed(0)} mm ruler band` : '') +
        `. Reduce the diameter, the margin, or turn off the calibration ruler.`;
    }
  }

  const requested = copies === undefined ? capacityPerPage : Math.max(0, Math.floor(copies));
  const pages = !fits ? 0 : Math.max(1, Math.ceil(requested / capacityPerPage));

  const usedW = cols > 0 ? cols * diameterMm + (cols - 1) * gapMm : 0;
  const originX = marginMm + Math.max(0, (usableW - usedW) / 2);

  return {
    paper,
    orientation,
    fits,
    reason,
    cols,
    rows,
    capacityPerPage,
    requested,
    totalBadges: fits ? Math.min(requested, capacityPerPage) : 0,
    pages,
    paperMm: { w, h },
    badgeDiameterMm: diameterMm,
    gapMm,
    marginMm,
    reserveTopMm,
    originMm: { x: originX, y: marginMm + reserveTopMm },
    stepMm: diameterMm + gapMm,
  };
}

/** Top-left corner (mm from the page's top-left) of the badge in `slot`. */
export function badgeOriginMm(layout: SheetLayout, slot: number): { x: number; y: number } {
  const col = slot % layout.cols;
  const row = Math.floor(slot / layout.cols);
  return {
    x: layout.originMm.x + col * layout.stepMm,
    y: layout.originMm.y + row * layout.stepMm,
  };
}

/** CSS `@page size` value for this paper, e.g. "210mm 297mm". */
export function pageSizeCss(paper: PaperSize, orientation: Orientation): string {
  const { w, h } = PAPER_SIZES_MM[paper];
  const [pw, ph] = orientation === 'portrait' ? [w, h] : [h, w];
  return `${pw}mm ${ph}mm`;
}
