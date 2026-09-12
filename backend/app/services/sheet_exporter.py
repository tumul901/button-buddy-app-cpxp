"""
PNG sheet exporter.

Renders the same geometry as the PDF exporter at PRINT_DPI so the on-screen
preview is a faithful picture of the printed page. The PDF remains the
accurate print artefact; this is for preview and for workflows that want a
bitmap.

Positions are computed in mm and converted once per badge, rather than by
multiplying a pre-rounded pixel step, so no rounding drift accumulates across
a row.
"""

import logging
import os
from typing import Sequence

from PIL import Image, ImageDraw, ImageFont

from app.config import MAX_EXPORT_PAGES, PRINT_DPI, RULER_BAND_MM
from app.services import ruler as ruler_spec
from app.services.compositor import open_image
from app.services.layout import badge_origin_mm, compute_layout
from app.services.pdf_exporter import cut_guide_positions
from app.services.units import mm_to_px

log = logging.getLogger(__name__)


def _dashed_circle(
    draw: ImageDraw.ImageDraw,
    cx: int,
    cy: int,
    r: int,
    width: int,
    fill: tuple[int, int, int],
    dash_deg: float = 4.0,
) -> None:
    """
    Pillow cannot stroke a dashed outline, so the ring is drawn as alternating
    arcs. Kept visually identical to the PDF's dashed cutter ring.
    """
    box = [cx - r, cy - r, cx + r, cy + r]
    angle = 0.0
    while angle < 360.0:
        draw.arc(box, angle, min(angle + dash_deg, 360.0), fill=fill, width=width)
        angle += dash_deg * 2.0


def _font(px: int) -> ImageFont.ImageFont:
    """
    A scalable font sized in *print* pixels.

    v1 used the bitmap default, which is 11 px tall — 0.85 mm at 300 DPI, so
    the calibration numbers the user is told to measure were unreadable.
    Pillow >= 10.1 gives a scalable default, which needs no shipped font file
    and behaves identically in the slim container.
    """
    try:
        return ImageFont.load_default(size=px)
    except TypeError:  # very old Pillow
        return ImageFont.load_default()


def _draw_ruler(draw: ImageDraw.ImageDraw, pw_mm: float, band_top_mm: float, dpi: int) -> None:
    g = ruler_spec.geometry(pw_mm, band_top_mm)
    x0 = mm_to_px(g.x0, dpi)
    baseline = mm_to_px(g.baseline_y, dpi)

    title_font = _font(mm_to_px(2.1, dpi))
    label_font = _font(mm_to_px(2.4, dpi))

    draw.text(
        (mm_to_px(pw_mm / 2.0, dpi), mm_to_px(g.title_y, dpi)),
        ruler_spec.TITLE,
        fill=(40, 40, 40),
        font=title_font,
        anchor="mm",
    )

    draw.line(
        [(x0, baseline), (mm_to_px(g.x1, dpi), baseline)],
        fill=(40, 40, 40),
        width=max(1, mm_to_px(0.18, dpi)),
    )

    for i, length in ruler_spec.ticks():
        tx = mm_to_px(g.x0 + i, dpi)
        major = i % 10 == 0
        draw.line(
            [(tx, baseline), (tx, baseline + mm_to_px(length, dpi))],
            fill=(40, 40, 40) if major else (110, 110, 110),
            width=max(1, mm_to_px(0.22 if major else 0.12, dpi)),
        )
        if major:
            draw.text(
                (tx, mm_to_px(g.label_y, dpi)),
                str(i),
                fill=(40, 40, 40),
                font=label_font,
                anchor="mm",
            )



def _dashed_line(
    draw: ImageDraw.ImageDraw,
    start: tuple[int, int],
    end: tuple[int, int],
    width: int,
    fill: tuple[int, int, int],
    dash_px: int,
) -> None:
    """A dashed straight line; Pillow cannot stroke dashes natively."""
    x0, y0 = start
    x1, y1 = end
    span = max(abs(x1 - x0), abs(y1 - y0))
    if span <= 0:
        return
    steps = max(1, span // max(1, dash_px * 2))
    for i in range(steps + 1):
        a = (i * dash_px * 2) / span
        b = min(1.0, (i * dash_px * 2 + dash_px) / span)
        if a >= 1.0:
            break
        draw.line(
            [
                (round(x0 + (x1 - x0) * a), round(y0 + (y1 - y0) * a)),
                (round(x0 + (x1 - x0) * b), round(y0 + (y1 - y0) * b)),
            ],
            fill=fill,
            width=width,
        )


def export_png_sheets(
    output_dir: str,
    filename_stem: str,
    paper: str,
    orientation: str,
    diameter_mm: float,
    bleed_mm: float,
    gap_mm: float,
    margin_mm: float,
    badge_images: Sequence[str],
    copies: int | None = None,
    include_ruler: bool = True,
    draw_guides: bool = True,
    perforation_mm: float = 0.0,
    dpi: int = PRINT_DPI,
) -> dict:
    """Render every page needed and return the list of written files."""
    if not badge_images:
        raise ValueError("badge_images must not be empty")

    has_bleed = bleed_mm > 0.0
    artwork_mm = diameter_mm + (2.0 * bleed_mm if has_bleed else 0.0)
    # Match the PDF: the cell holds whichever is larger, artwork or cutter ring.
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
        items = items[:max_items]

    sheet_w = mm_to_px(pw_mm, dpi)
    sheet_h = mm_to_px(ph_mm, dpi)
    artwork_px = mm_to_px(artwork_mm, dpi)
    badge_px = mm_to_px(diameter_mm, dpi)

    cache: dict[str, Image.Image] = {}
    os.makedirs(output_dir, exist_ok=True)

    written: list[str] = []
    total_pages = max(1, -(-len(items) // capacity))

    for page in range(total_pages):
        sheet = Image.new("RGB", (sheet_w, sheet_h), (255, 255, 255))
        draw = ImageDraw.Draw(sheet)

        if include_ruler:
            _draw_ruler(draw, pw_mm, margin_mm, dpi)

        # Cut guides tangent to the rings, on BOTH axes, spanning the sheet.
        if perforation_mm > 0:
            xs, ys = cut_guide_positions(layout, cell_mm, diameter_mm + perforation_mm)
            stroke = max(1, mm_to_px(0.14, dpi))
            dash = mm_to_px(1.1, dpi)
            for x_mm in xs:
                if -0.01 <= x_mm <= pw_mm + 0.01:
                    x = mm_to_px(x_mm, dpi)
                    _dashed_line(draw, (x, 0), (x, sheet_h), stroke, (125, 125, 125), dash)
            for y_mm in ys:
                if -0.01 <= y_mm <= ph_mm + 0.01:
                    y = mm_to_px(y_mm, dpi)
                    _dashed_line(draw, (0, y), (sheet_w, y), stroke, (125, 125, 125), dash)

        for slot in range(capacity):
            idx = page * capacity + slot
            if idx >= len(items):
                break
            path = items[idx]
            if path not in cache:
                img = open_image(path).convert("RGBA")
                if img.size != (artwork_px, artwork_px):
                    img = img.resize((artwork_px, artwork_px), Image.LANCZOS)
                cache[path] = img

            x_mm, y_mm = badge_origin_mm(layout, slot)
            cx = mm_to_px(x_mm + cell_mm / 2.0, dpi)
            cy = mm_to_px(y_mm + cell_mm / 2.0, dpi)
            # Artwork is centred in the cell; the cell may be larger than the
            # artwork when the cutter ring is the outermost element.
            sheet.paste(
                cache[path],
                (cx - artwork_px // 2, cy - artwork_px // 2),
                cache[path],
            )

            if perforation_mm > 0:
                _dashed_circle(
                    draw,
                    cx,
                    cy,
                    mm_to_px((diameter_mm + perforation_mm) / 2.0, dpi),
                    max(1, mm_to_px(0.16, dpi)),
                    (115, 115, 115),
                )

            if draw_guides:
                r = badge_px // 2
                draw.ellipse(
                    [cx - r, cy - r, cx + r, cy + r],
                    outline=(160, 160, 160),
                    width=max(1, mm_to_px(0.12, dpi)),
                )

        suffix = "" if total_pages == 1 else f"_p{page + 1}"
        path = os.path.join(output_dir, f"{filename_stem}{suffix}.png")
        sheet.save(path, "PNG", dpi=(dpi, dpi))
        written.append(path)

    return {
        "files": written,
        "total_pages": total_pages,
        "badges_placed": len(items),
        "truncated": truncated,
        "layout": layout,
        "sheet_px": {"w": sheet_w, "h": sheet_h},
    }
