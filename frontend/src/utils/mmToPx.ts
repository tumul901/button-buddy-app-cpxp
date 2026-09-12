/**
 * mm → pixels conversion for print-resolution canvas generation.
 *
 * WHY 25.4?
 * ---------
 * 1 inch = 25.4 mm  (exact SI definition, international agreement 1959)
 *
 * Screens and printers express resolution in DPI (dots per inch),
 * not dots per millimetre. To convert a physical mm size into pixels:
 *
 *   pixels = mm ÷ 25.4 × DPI
 *          = mm × (DPI / 25.4)
 *
 * Step by step:
 *   mm / 25.4   →  converts millimetres into inches
 *   inches × DPI →  converts inches into pixels/dots
 *
 * We use PRINT_DPI = 300 because:
 *   - 300 dpi is the industry minimum for photo-quality badge print
 *   - At 300 dpi, 58 mm → 685 px (sharp enough for a ~6 cm button badge)
 *   - Below 300 dpi circles appear jagged after cutting
 *
 * HOW PRINT ACCURACY IS ENFORCED:
 *   - Canvas is generated at 685 × 685 px (at 300 dpi for 58 mm)
 *   - In @media print we set CSS: width: 58mm; height: 58mm
 *   - The browser maps exactly 685 px → 58 mm on paper at print time
 *   - We never assume screen DPI — CSS mm handles the screen side
 */

export const PRINT_DPI = 300;

/**
 * Convert millimetres to pixels at the target DPI.
 * Default DPI is PRINT_DPI (300) for print-resolution canvas generation.
 */
export function mmToPx(mm: number, dpi: number = PRINT_DPI): number {
  return Math.round(mm * (dpi / 25.4));
}

/**
 * Convert pixels back to millimetres at the target DPI.
 */
export function pxToMm(px: number, dpi: number = PRINT_DPI): number {
  return (px / dpi) * 25.4;
}

/** Human-readable canvas size string for UI hints */
export function canvasSizeLabel(mm: number): string {
  const px = mmToPx(mm);
  return `${px} × ${px} px @ ${PRINT_DPI} DPI`;
}
