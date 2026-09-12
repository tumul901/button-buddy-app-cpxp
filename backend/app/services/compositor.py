"""
Pillow-based badge compositor.

GEOMETRY CONTRACT (shared with frontend/src/components/TemplateEditor)
----------------------------------------------------------------------
  badge_px = round(diameter_mm * DPI / 25.4)      the trim circle
  bleed_px = round(bleed_mm   * DPI / 25.4)       ink beyond the trim
  total_px = badge_px + 2 * bleed_px              the artwork square

The photo is always cover-fitted to `total_px` — the full artwork square,
bleed included. The editor preview sizes its box to the same total diameter
and uses `object-fit: cover`, so preview and render agree exactly.

CROP IS NORMALISED
------------------
`crop_offset_x/y` are fractions of the *total* diameter, not pixels:

    paste_x = (total_px - scaled_w) / 2 + offset_x * total_px

v1 sent raw CSS pixels and converted with a hardcoded 300/96 ratio, which
silently broke the moment the preview element was any size other than
`diameter_mm * 3.779528` px. Fractions are resolution-independent: the
preview can be any size, responsive included, and the render still matches.

`crop_scale` is a multiplier on top of cover-fit. 1.0 means "exactly covers
the circle"; values below 1.0 would expose the background and are clamped.
"""

import logging
import os

from PIL import Image, ImageDraw, ImageOps

from app.config import MAX_IMAGE_PIXELS, PRINT_DPI
from app.services.units import mm_to_px

log = logging.getLogger(__name__)

# Pillow's own bomb guard. Above 2x this it raises instead of warning.
Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS

MIN_SCALE = 1.0
MAX_SCALE = 8.0


class CompositeError(RuntimeError):
    """Raised when source artwork cannot be composited."""


def open_image(path: str) -> Image.Image:
    """Open an image defensively, applying EXIF rotation."""
    try:
        img = Image.open(path)
        img.load()
    except Image.DecompressionBombError as exc:
        raise CompositeError(f"Image is too large to process: {exc}") from exc
    except (OSError, ValueError) as exc:
        raise CompositeError(f"Could not read image {os.path.basename(path)}: {exc}") from exc
    # Phone photos carry rotation in EXIF; without this faces come out sideways.
    return ImageOps.exif_transpose(img)


def fit_cover(img: Image.Image, size: int) -> Image.Image:
    """Scale + centre-crop to an exact `size` x `size` square (CSS object-fit: cover)."""
    scale = max(size / img.width, size / img.height)
    w = max(1, round(img.width * scale))
    h = max(1, round(img.height * scale))
    resized = img.resize((w, h), Image.LANCZOS)
    left = (w - size) // 2
    top = (h - size) // 2
    return resized.crop((left, top, left + size, top + size))


def clamp_offsets(
    offset_x: float,
    offset_y: float,
    scale: float,
    photo_w: int,
    photo_h: int,
) -> tuple[float, float]:
    """
    Keep the photo covering the circle. Panning past the edge would expose
    background as a white sliver inside the badge — always a defect, never
    something the user meant.

    With cover-fit, the scaled photo is `total * scale` in the limiting
    dimension and `total * scale * aspect` in the other, so the maximum
    offset as a fraction of the total diameter is (extent - 1) / 2.
    """
    if photo_w <= 0 or photo_h <= 0:
        return 0.0, 0.0
    long_over_short = max(photo_w, photo_h) / min(photo_w, photo_h)
    extent_x = scale * (long_over_short if photo_w >= photo_h else 1.0)
    extent_y = scale * (long_over_short if photo_h > photo_w else 1.0)
    max_x = max(0.0, (extent_x - 1.0) / 2.0)
    max_y = max(0.0, (extent_y - 1.0) / 2.0)
    return (
        max(-max_x, min(max_x, offset_x)),
        max(-max_y, min(max_y, offset_y)),
    )


def composite_badge(
    photo_path: str,
    template_path: str | None,
    diameter_mm: float,
    bleed_mm: float,
    crop_offset_x: float,
    crop_offset_y: float,
    crop_scale: float,
    output_path: str,
    dpi: int = PRINT_DPI,
    draw_guides: bool = True,
) -> dict:
    """
    Composite a user photo + branding template into a print-ready badge PNG.

    The saved image is exactly `total_px` square and carries `dpi` metadata, so
    the artwork measures `diameter_mm + 2*bleed_mm` when placed at 100% scale.
    """
    badge_px = mm_to_px(diameter_mm, dpi)
    has_bleed = bleed_mm > 0.0
    bleed_px = mm_to_px(bleed_mm, dpi) if has_bleed else 0
    total_px = badge_px + bleed_px * 2
    if total_px < 8:
        raise CompositeError(f"Badge diameter {diameter_mm} mm is too small to render")

    scale = max(MIN_SCALE, min(MAX_SCALE, float(crop_scale)))

    # ---- 1. Photo: cover-fit the full artwork square, then pan/zoom --------
    photo = open_image(photo_path).convert("RGBA")
    offset_x, offset_y = clamp_offsets(
        crop_offset_x, crop_offset_y, scale, photo.width, photo.height
    )

    cover = max(total_px / photo.width, total_px / photo.height)
    effective = cover * scale
    scaled_w = max(1, round(photo.width * effective))
    scaled_h = max(1, round(photo.height * effective))
    photo_resized = photo.resize((scaled_w, scaled_h), Image.LANCZOS)

    canvas = Image.new("RGBA", (total_px, total_px), (255, 255, 255, 0))
    paste_x = round((total_px - scaled_w) / 2 + offset_x * total_px)
    paste_y = round((total_px - scaled_h) / 2 + offset_y * total_px)
    canvas.paste(photo_resized, (paste_x, paste_y))

    # ---- 2. Circular mask over the whole artwork square --------------------
    # Supersampled 4x so the cut edge is smooth rather than stair-stepped;
    # a jagged rim is obvious once a badge press crops to it.
    ss = 4
    mask = Image.new("L", (total_px * ss, total_px * ss), 0)
    ImageDraw.Draw(mask).ellipse([0, 0, total_px * ss - 1, total_px * ss - 1], fill=255)
    mask = mask.resize((total_px, total_px), Image.LANCZOS)
    canvas.putalpha(mask)

    # ---- 3. Branding template over the photo -------------------------------
    if template_path and os.path.exists(template_path):
        template = open_image(template_path).convert("RGBA")
        # Cover, not stretch: a non-square template must not be distorted.
        template = fit_cover(template, total_px)
        tpl_alpha = template.split()[3]
        tpl_alpha = Image.composite(tpl_alpha, Image.new("L", (total_px, total_px), 0), mask)
        template.putalpha(tpl_alpha)
        result = Image.alpha_composite(canvas, template)
    else:
        result = canvas

    # ---- 4. Trim guide -----------------------------------------------------
    # Only meaningful when there is bleed: it marks where to cut inside the art.
    # Without bleed the artwork edge *is* the trim line, so drawing a ring there
    # just eats 2 px of the user's photo.
    if draw_guides and has_bleed:
        ImageDraw.Draw(result).ellipse(
            [bleed_px, bleed_px, bleed_px + badge_px - 1, bleed_px + badge_px - 1],
            outline=(200, 40, 40, 160),
            width=max(1, round(badge_px / 400)),
        )

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    result.save(output_path, "PNG", dpi=(dpi, dpi))

    return {
        "badge_px": badge_px,
        "bleed_px": bleed_px,
        "total_px": total_px,
        "diameter_mm": diameter_mm,
        "bleed_mm": bleed_mm if has_bleed else 0.0,
        "total_diameter_mm": diameter_mm + (2.0 * bleed_mm if has_bleed else 0.0),
        "dpi": dpi,
        "crop": {"offset_x": offset_x, "offset_y": offset_y, "scale": scale},
    }
