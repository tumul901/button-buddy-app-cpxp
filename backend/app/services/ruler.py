"""
Calibration ruler.

A 50.0 mm scale printed at the top of every sheet. The user measures it with a
physical ruler to prove the printer did not silently rescale the page
("Fit to Printable Area" is on by default in most print dialogs and shrinks
output by 4-8%). If the bar measures 50 mm, every badge is exact too.

Geometry is defined once, in mm, from the top-left of the page, and rendered by
both the PDF and PNG exporters so the two sheets are identical. It occupies a
reserved band (config.RULER_BAND_MM) that `compute_layout` subtracts from the
usable height — v1 drew it over the page and it collided with the first badge
row at any margin below 10 mm.
"""

from dataclasses import dataclass

RULER_MM = 50.0

# Offsets within the band, mm from the top of the band.
TITLE_DY = 2.6
BASELINE_DY = 5.6
TICK_MAJOR = 3.0
TICK_MID = 2.0
TICK_MINOR = 1.1
LABEL_DY = 11.2

TITLE = "50.0 mm CALIBRATION BAR  —  MUST MEASURE 50 mm  ·  PRINT AT 100% / ACTUAL SIZE"


@dataclass(frozen=True)
class RulerGeometry:
    x0: float  # left end, mm from page left
    baseline_y: float  # mm from page top
    title_y: float
    label_y: float
    length: float = RULER_MM

    @property
    def x1(self) -> float:
        return self.x0 + self.length


def geometry(paper_w_mm: float, band_top_mm: float) -> RulerGeometry:
    """Ruler placement for a page of the given width, band starting at `band_top_mm`."""
    return RulerGeometry(
        x0=(paper_w_mm - RULER_MM) / 2.0,
        baseline_y=band_top_mm + BASELINE_DY,
        title_y=band_top_mm + TITLE_DY,
        label_y=band_top_mm + LABEL_DY,
    )


def ticks() -> list[tuple[int, float]]:
    """(millimetre index, tick length in mm) for all 51 marks."""
    out = []
    for i in range(int(RULER_MM) + 1):
        if i % 10 == 0:
            out.append((i, TICK_MAJOR))
        elif i % 5 == 0:
            out.append((i, TICK_MID))
        else:
            out.append((i, TICK_MINOR))
    return out
