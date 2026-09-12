"""
Sheet layout calculator.

Computes how many badges fit on a sheet. All inputs and outputs are mm.

CAPACITY FORMULA
----------------
N badges in a row occupy  N*d + (N-1)*gap  — the last badge has no gap after it.
Solving  N*d + (N-1)*gap <= usable  gives:

    N = floor((usable + gap) / (d + gap))

The naive  floor(usable / (d + gap))  charges a trailing gap to the last badge
and undercounts: on US Letter at 58 mm with a 10 mm gap it reports 6 badges
where 9 actually fit — a third of the sheet wasted.

This module is mirrored by frontend/src/utils/paperLayouts.ts. The two are kept
in lockstep by tests/test_layout.py::test_matches_frontend_vectors.
"""

from typing import Literal

PaperSize = Literal["A4", "A3", "Letter", "Legal", "4x6"]
Orientation = Literal["portrait", "landscape"]

PAPER_SIZES_MM: dict[str, dict[str, float]] = {
    "A4": {"w": 210.0, "h": 297.0},
    "A3": {"w": 297.0, "h": 420.0},
    "Letter": {"w": 215.9, "h": 279.4},
    "Legal": {"w": 215.9, "h": 355.6},
    "4x6": {"w": 101.6, "h": 152.4},
}

# Accepted aliases -> canonical key.
PAPER_ALIASES = {"4x6in": "4x6", "4X6": "4x6", "letter": "Letter", "legal": "Legal"}


def normalize_paper(paper: str) -> str:
    key = PAPER_ALIASES.get(paper, paper)
    if key not in PAPER_SIZES_MM:
        raise ValueError(f"Unknown paper size: {paper!r}")
    return key


def fit_count(usable_mm: float, size_mm: float, gap_mm: float) -> int:
    """How many `size_mm` items fit in `usable_mm` with `gap_mm` between them."""
    if size_mm <= 0 or usable_mm < size_mm:
        return 0
    return int((usable_mm + gap_mm + 1e-9) // (size_mm + gap_mm))


def compute_layout(
    paper: str,
    diameter_mm: float,
    gap_mm: float,
    margin_mm: float,
    orientation: str = "portrait",
    copies: int | None = None,
    reserve_top_mm: float = 0.0,
) -> dict:
    """
    Calculate badge tiling on a sheet.

    `diameter_mm` is the *effective* badge size including any bleed — i.e. the
    footprint the artwork actually occupies on paper.

    `reserve_top_mm` is a band at the top of the page (used by the calibration
    ruler) that badges must not intrude into. It consumes layout space rather
    than being drawn over the grid.

    Returns `fits: False` with a human-readable `reason` when nothing fits,
    instead of pretending one badge fits and drawing it off the page.
    """
    key = normalize_paper(paper)
    p = dict(PAPER_SIZES_MM[key])
    if orientation == "landscape":
        p["w"], p["h"] = p["h"], p["w"]

    usable_w = p["w"] - margin_mm * 2
    usable_h = p["h"] - margin_mm * 2 - reserve_top_mm

    cols = fit_count(usable_w, diameter_mm, gap_mm)
    rows = fit_count(usable_h, diameter_mm, gap_mm)
    capacity = cols * rows

    fits = capacity > 0
    reason = ""
    if not fits:
        if usable_w < diameter_mm:
            reason = (
                f"A {diameter_mm:.1f} mm badge does not fit across "
                f"{key} {orientation} ({p['w']:.1f} mm) with {margin_mm:.1f} mm margins. "
                f"Reduce the diameter or the margin."
            )
        else:
            reason = (
                f"A {diameter_mm:.1f} mm badge does not fit down "
                f"{key} {orientation} ({p['h']:.1f} mm) with {margin_mm:.1f} mm margins"
                + (f" and a {reserve_top_mm:.0f} mm ruler band" if reserve_top_mm else "")
                + ". Reduce the diameter, the margin, or turn off the calibration ruler."
            )

    requested = capacity if copies is None else max(0, int(copies))
    pages = 0 if not fits else max(1, -(-requested // capacity))  # ceil div

    # Grid origin (top-left of the first badge), from the top-left of the page.
    origin_x = margin_mm
    origin_y = margin_mm + reserve_top_mm

    # Centre the grid horizontally in the leftover space so sheets look deliberate.
    used_w = cols * diameter_mm + max(0, cols - 1) * gap_mm if cols else 0.0
    origin_x += max(0.0, (usable_w - used_w) / 2.0)

    return {
        "paper": key,
        "orientation": orientation,
        "fits": fits,
        "reason": reason,
        "cols": cols,
        "rows": rows,
        "capacity_per_page": capacity,
        "requested": requested,
        "total_badges": min(requested, capacity) if fits else 0,
        "pages": pages,
        "paper_mm": p,
        "badge_diameter_mm": diameter_mm,
        "gap_mm": gap_mm,
        "margin_mm": margin_mm,
        "reserve_top_mm": reserve_top_mm,
        "origin_mm": {"x": origin_x, "y": origin_y},
        "step_mm": diameter_mm + gap_mm,
    }


def badge_origin_mm(layout: dict, slot: int) -> tuple[float, float]:
    """
    Top-left corner (mm from the page's top-left) of the badge in `slot`
    on its page. Computed from unrounded mm so positions never accumulate
    rounding drift across a row.
    """
    cols = layout["cols"]
    if cols <= 0:
        raise ValueError("layout has no columns")
    col = slot % cols
    row = slot // cols
    step = layout["step_mm"]
    return (
        layout["origin_mm"]["x"] + col * step,
        layout["origin_mm"]["y"] + row * step,
    )
