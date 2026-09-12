"""
PDF exporter (ReportLab).

WHY PDF IS THE ACCURATE PRINT PATH
----------------------------------
PDF stores geometry in points: 1 pt = 1/72 inch, so mm -> pt is
`mm / 25.4 * 72`, exact and printer-agnostic. A 58 mm badge is written as
164.4094 pt and every conforming renderer reproduces it at 58 mm when printed
at 100% scale. Nothing depends on screen DPI, browser print margins, or the
OS print dialog.

By contrast the browser `window.print()` path can only ever be as accurate as
the page box the browser hands us, which is why the PDF is the default here
and the browser path is explicitly labelled as a preview.

Each badge is drawn as:
  - the raster composite, placed at exact mm coordinates
  - a vector trim circle at exactly `diameter_mm`
  - four quadrant registration ticks for aligning a punch cutter
"""

import logging
from typing import Optional, Sequence

from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas as rl_canvas

from app.config import MAX_EXPORT_PAGES, RULER_BAND_MM
from app.services import ruler as ruler_spec
from app.services.layout import badge_origin_mm, compute_layout

log = logging.getLogger(__name__)


def _y(page_h_mm: float, y_top_mm: float) -> float:
    """mm-from-top -> PDF points-from-bottom."""
    return (page_h_mm - y_top_mm) * mm


def _draw_ruler(c: rl_canvas.Canvas, pw_mm: float, ph_mm: float, band_top_mm: float) -> None:
    g = ruler_spec.geometry(pw_mm, band_top_mm)
    c.saveState()

    c.setFont("Helvetica-Bold", 5.6)
    c.setFillColorRGB(0.15, 0.15, 0.15)
    c.drawCentredString(pw_mm * mm / 2.0, _y(ph_mm, g.title_y), ruler_spec.TITLE)

    baseline = _y(ph_mm, g.baseline_y)
    c.setStrokeColorRGB(0.15, 0.15, 0.15)
    c.setLineWidth(0.5)
    c.line(g.x0 * mm, baseline, g.x1 * mm, baseline)

    for i, length in ruler_spec.ticks():
        tx = (g.x0 + i) * mm
        c.setLineWidth(0.6 if i % 10 == 0 else 0.35)
        c.line(tx, baseline, tx, baseline - length * mm)

    c.setFont("Helvetica", 5.0)
    for i, _ in ruler_spec.ticks():
        if i % 10 == 0:
            c.drawCentredString((g.x0 + i) * mm, _y(ph_mm, g.label_y), str(i))

    c.restoreState()


def _draw_badge(
    c: rl_canvas.Canvas,
    reader: ImageReader,
    ph_mm: float,
    x_mm: float,
    y_top_mm: float,
    cell_mm: float,
    artwork_mm: float,
    diameter_mm: float,
    perforation_mm: float,
    draw_guides: bool,
) -> None:
    """
    Place one badge inside its layout cell.

    `cell_mm`   - the full slot, large enough for artwork AND the cutter ring
    `artwork_mm`- the printed image (trim + bleed)
    `diameter_mm` - the trim circle
    `perforation_mm` - EXTRA diameter beyond the trim for the cutter ring
    """
    cx = (x_mm + cell_mm / 2.0) * mm
    cy = _y(ph_mm, y_top_mm + cell_mm / 2.0)

    art_pt = artwork_mm * mm
    # preserveAspectRatio is deliberately False: composites are always square by
    # construction, and letterboxing here would silently shrink the badge.
    c.drawImage(
        reader,
        cx - art_pt / 2.0,
        cy - art_pt / 2.0,
        width=art_pt,
        height=art_pt,
        mask="auto",
    )

    if not draw_guides and perforation_mm <= 0:
        return

    r = (diameter_mm / 2.0) * mm

    c.saveState()

    if perforation_mm > 0:
        # The cutter ring: the paper disc the press actually needs, which is
        # wider than the badge so the rim can fold around the shell. Dashed so
        # it reads as "cut here", never as artwork.
        perf_r = ((diameter_mm + perforation_mm) / 2.0) * mm
        c.setStrokeColorRGB(0.45, 0.45, 0.45)
        c.setLineWidth(0.45)
        c.setDash(2.0, 2.0)
        c.circle(cx, cy, perf_r, stroke=1, fill=0)
        c.setDash()

    if draw_guides:
        c.setStrokeColorRGB(0.62, 0.62, 0.62)
        c.setLineWidth(0.35)
        c.circle(cx, cy, r, stroke=1, fill=0)

        # Registration ticks sit outside whichever ring is outermost.
        outer = max(r, ((diameter_mm + perforation_mm) / 2.0) * mm)
        tick = 2.2 * mm
        gap = 0.8 * mm
        c.setStrokeColorRGB(0.4, 0.4, 0.4)
        c.setLineWidth(0.45)
        c.line(cx, cy + outer + gap, cx, cy + outer + gap + tick)
        c.line(cx, cy - outer - gap, cx, cy - outer - gap - tick)
        c.line(cx - outer - gap, cy, cx - outer - gap - tick, cy)
        c.line(cx + outer + gap, cy, cx + outer + gap + tick, cy)

    c.restoreState()



def cut_guide_positions(
    layout: dict, cell_mm: float, ring_mm: float
) -> tuple[list[float], list[float]]:
    """
    Tangent cut-guide positions: (vertical x's, horizontal y-from-top's).

    Guides are emitted on BOTH axes so each badge ends up inside its own
    tangent square whatever the layout does. Emitting only verticals — as the
    first version did — is correct for a single column of stacked badges but
    wrong the moment the grid is a row, e.g. two badges side by side on a
    landscape 4x6, where the useful cut is horizontal.
    """
    if ring_mm <= 0:
        return [], []

    xs: list[float] = []
    for col in range(max(0, layout["cols"])):
        centre = layout["origin_mm"]["x"] + col * layout["step_mm"] + cell_mm / 2.0
        xs += [centre - ring_mm / 2.0, centre + ring_mm / 2.0]

    ys: list[float] = []
    for row in range(max(0, layout["rows"])):
        centre = layout["origin_mm"]["y"] + row * layout["step_mm"] + cell_mm / 2.0
        ys += [centre - ring_mm / 2.0, centre + ring_mm / 2.0]

    # Neighbouring rings that touch produce two guides in the same place.
    def dedupe(values: list[float]) -> list[float]:
        out: list[float] = []
        for v in sorted(values):
            if not out or abs(v - out[-1]) > 0.2:
                out.append(v)
        return out

    return dedupe(xs), dedupe(ys)


def _draw_cut_guides(
    c: rl_canvas.Canvas,
    layout: dict,
    pw_mm: float,
    ph_mm: float,
    cell_mm: float,
    ring_mm: float,
) -> None:
    """
    Dashed guides tangent to the cutter rings, spanning the whole sheet.

    The operator lines the sheet up against these in the cutting machine, so
    they must run edge to edge rather than stopping at the artwork. Same
    "cut here" ink as the rings themselves.
    """
    xs, ys = cut_guide_positions(layout, cell_mm, ring_mm)
    if not xs and not ys:
        return

    c.saveState()
    c.setStrokeColorRGB(0.45, 0.45, 0.45)
    c.setLineWidth(0.4)
    c.setDash(3.0, 2.5)
    for x_mm in xs:
        if -0.01 <= x_mm <= pw_mm + 0.01:
            c.line(x_mm * mm, 0, x_mm * mm, ph_mm * mm)
    for y_mm in ys:
        if -0.01 <= y_mm <= ph_mm + 0.01:
            y = _y(ph_mm, y_mm)
            c.line(0, y, pw_mm * mm, y)
    c.setDash()
    c.restoreState()


def export_pdf(
    output_path: str,
    paper: str,
    orientation: str,
    diameter_mm: float,
    bleed_mm: float,
    gap_mm: float,
    margin_mm: float,
    badge_images: Sequence[str],
    copies: Optional[int] = None,
    include_ruler: bool = True,
    draw_guides: bool = True,
    perforation_mm: float = 0.0,
) -> dict:
    """
    Tile `badge_images` across as many pages as needed.

    `badge_images` is the already-expanded placement sequence (one entry per
    printed badge). `copies` only applies when a single image is repeated to
    fill the sheet.
    """
    if not badge_images:
        raise ValueError("badge_images must not be empty")

    has_bleed = bleed_mm > 0.0
    artwork_mm = diameter_mm + (2.0 * bleed_mm if has_bleed else 0.0)
    # The cell must hold whichever is larger: the printed artwork, or the
    # cutter ring. Sizing it to the artwork alone would let adjacent
    # perforation circles overlap each other and run off the page.
    cell_mm = max(artwork_mm, diameter_mm + perforation_mm)
    band = RULER_BAND_MM if include_ruler else 0.0

    layout = compute_layout(
        paper=paper,
        diameter_mm=cell_mm,
        gap_mm=gap_mm,
        margin_mm=margin_mm,
        orientation=orientation,
        copies=None,
        reserve_top_mm=band,
    )
    if not layout["fits"]:
        raise ValueError(layout["reason"])

    capacity = layout["capacity_per_page"]
    pw_mm = layout["paper_mm"]["w"]
    ph_mm = layout["paper_mm"]["h"]

    if len(badge_images) == 1 and copies is not None:
        items = list(badge_images) * max(1, copies)
    elif len(badge_images) == 1 and copies is None:
        items = list(badge_images) * capacity
    else:
        items = list(badge_images)

    max_items = capacity * MAX_EXPORT_PAGES
    truncated = len(items) > max_items
    if truncated:
        log.warning("export truncated from %d to %d badges", len(items), max_items)
        items = items[:max_items]

    # One ImageReader per distinct file: v1 re-decoded the PNG for every
    # placement, so a 12-up sheet decoded the same image 12 times.
    readers: dict[str, ImageReader] = {}

    c = rl_canvas.Canvas(output_path, pagesize=(pw_mm * mm, ph_mm * mm))
    c.setTitle(f"Button Buddy - {diameter_mm:.1f} mm badges")
    c.setAuthor("Button Buddy")
    c.setSubject(
        f"{len(items)} x {diameter_mm:.1f} mm badge"
        f"{f' + {bleed_mm:.1f} mm bleed' if has_bleed else ''} on {layout['paper']} {orientation}"
    )

    pages = 0
    for idx, path in enumerate(items):
        slot = idx % capacity
        if slot == 0:
            if idx > 0:
                c.showPage()
            pages += 1
            if include_ruler:
                _draw_ruler(c, pw_mm, ph_mm, margin_mm)
            if perforation_mm > 0:
                _draw_cut_guides(
                    c, layout, pw_mm, ph_mm, cell_mm, diameter_mm + perforation_mm
                )

        if path not in readers:
            readers[path] = ImageReader(path)

        x_mm, y_top_mm = badge_origin_mm(layout, slot)
        _draw_badge(
            c,
            readers[path],
            ph_mm,
            x_mm,
            y_top_mm,
            cell_mm,
            artwork_mm,
            diameter_mm,
            perforation_mm,
            draw_guides,
        )

    c.save()

    return {
        "pdf_path": output_path,
        "badges_placed": len(items),
        "total_pages": pages,
        "truncated": truncated,
        "layout": layout,
        "page_size_pt": {"w": pw_mm * mm, "h": ph_mm * mm},
    }
