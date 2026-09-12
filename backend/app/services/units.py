"""
mm_to_px conversion utility.

WHY 25.4?
---------
1 inch = 25.4 mm exactly (SI international agreement, 1959).
Printers and screens measure resolution in DPI (dots per inch), not per mm.
To convert a physical mm size into a pixel count at a given DPI:

    pixels = mm × (DPI / 25.4)

Breaking it down:
  - mm / 25.4  →  converts millimetres into inches
  - inches × DPI  →  converts inches into dots/pixels

We use PRINT_DPI = 300 because:
  - 300 dpi is the industry standard for photo-quality badge printing
  - Below 300 dpi, circles appear jagged when cut by a badge press
  - At 300 dpi, 58 mm → 685 px (sharp, sufficient for a ~6 cm badge)
"""

from app.config import PRINT_DPI


def mm_to_px(mm: float, dpi: int = PRINT_DPI) -> int:
    """Convert millimetres to pixels at the given DPI."""
    return round(mm * dpi / 25.4)


def px_to_mm(px: int, dpi: int = PRINT_DPI) -> float:
    """Convert pixels back to millimetres at the given DPI."""
    return (px / dpi) * 25.4
