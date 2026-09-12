/**
 * Auto-fit: find the settings that get the most badges onto one sheet.
 *
 * Fitting more is a search over margin, gap and the calibration ruler, and
 * the interactions are not obvious. On 4x6 for example, two 58 mm badges with
 * a 12 mm cutter ring need 140 mm of a 152.4 mm sheet — so they fit only once
 * the 12 mm ruler band is dropped. Expecting a user to discover that by
 * dragging three sliders is a bad trade; the app can just work it out.
 *
 * The ruler is only sacrificed when it is genuinely the blocker, and the
 * caller is told, because the ruler is the one thing that proves the printer
 * did not rescale the page.
 */

import type { Orientation, PaperSize } from './paperLayouts';
import { RULER_BAND_MM, cellSizeMm, computeLayout } from './paperLayouts';

export interface FitInput {
  paper: PaperSize;
  orientation: Orientation;
  diameterMm: number;
  bleedMm: number;
  perforationMm: number;
  marginMm: number;
  gapMm: number;
  includeRuler: boolean;
}

export interface FitResult {
  marginMm: number;
  gapMm: number;
  includeRuler: boolean;
  orientation: Orientation;
  capacity: number;
  /** Capacity with the settings the user currently has. */
  currentCapacity: number;
  improved: boolean;
  /** Plain-language list of what would change. */
  changes: string[];
}

/** Smallest margin worth printing to: most printers cannot reach the last few mm. */
const MIN_SAFE_MARGIN_MM = 3;

function capacityFor(
  input: FitInput,
  marginMm: number,
  gapMm: number,
  includeRuler: boolean,
  orientation: Orientation,
): number {
  const layout = computeLayout(
    input.paper,
    orientation,
    cellSizeMm(input.diameterMm, input.bleedMm, input.perforationMm),
    gapMm,
    marginMm,
    undefined,
    includeRuler ? RULER_BAND_MM : 0,
  );
  return layout.fits ? layout.capacityPerPage : 0;
}

/**
 * Search for the best arrangement.
 *
 * Candidates are ordered so that ties prefer the *least* disruptive change:
 * keep the ruler, keep the orientation, keep generous margins and gaps.
 */
export function findBestFit(input: FitInput, allowRotate = true): FitResult {
  const currentCapacity = capacityFor(
    input,
    input.marginMm,
    input.gapMm,
    input.includeRuler,
    input.orientation,
  );

  const margins = [10, 8, 6, 5, 4, MIN_SAFE_MARGIN_MM].filter((m) => m <= Math.max(10, input.marginMm));
  const gaps = [5, 4, 3, 2];
  const orientations: Orientation[] = allowRotate
    ? [input.orientation, input.orientation === 'portrait' ? 'landscape' : 'portrait']
    : [input.orientation];

  let best: FitResult = {
    marginMm: input.marginMm,
    gapMm: input.gapMm,
    includeRuler: input.includeRuler,
    orientation: input.orientation,
    capacity: currentCapacity,
    currentCapacity,
    improved: false,
    changes: [],
  };

  // Ruler kept first: it is only given up if nothing else gets there.
  for (const ruler of [true, false]) {
    if (!ruler && !input.includeRuler) continue; // already off; no change to report
    for (const orientation of orientations) {
      for (const margin of margins) {
        for (const gap of gaps) {
          const capacity = capacityFor(input, margin, gap, ruler, orientation);
          if (capacity <= best.capacity) continue;

          const changes: string[] = [];
          if (orientation !== input.orientation) changes.push(`rotated to ${orientation}`);
          if (Math.abs(margin - input.marginMm) > 0.01) changes.push(`margin ${margin} mm`);
          if (Math.abs(gap - input.gapMm) > 0.01) changes.push(`gap ${gap} mm`);
          if (ruler !== input.includeRuler) {
            changes.push(ruler ? 'calibration ruler on' : 'calibration ruler off');
          }

          best = {
            marginMm: margin,
            gapMm: gap,
            includeRuler: ruler,
            orientation,
            capacity,
            currentCapacity,
            improved: true,
            changes,
          };
        }
      }
    }
    // If keeping the ruler already improved things, do not bother dropping it.
    if (best.improved && best.includeRuler) break;
  }

  return best;
}
