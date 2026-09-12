"""
Compositor — the crop contract shared with the editor preview.

Offsets are fractions of the badge diameter, so the same numbers describe the
same framing whatever size the preview happens to be on screen.
"""

import pytest
from PIL import Image

from app.services.compositor import (
    CompositeError,
    clamp_offsets,
    composite_badge,
    fit_cover,
)
from app.services.units import mm_to_px


def _make(tmp_path, photo, template=None, **kw):
    out = tmp_path / "badge.png"
    info = composite_badge(
        photo_path=photo,
        template_path=template,
        diameter_mm=kw.pop("diameter_mm", 58.0),
        bleed_mm=kw.pop("bleed_mm", 0.0),
        crop_offset_x=kw.pop("offset_x", 0.0),
        crop_offset_y=kw.pop("offset_y", 0.0),
        crop_scale=kw.pop("scale", 1.0),
        output_path=str(out),
        **kw,
    )
    return str(out), info


# --------------------------------------------------------------------------
# Cover fit
# --------------------------------------------------------------------------


def test_fit_cover_returns_exact_square():
    for w, h in ((600, 1500), (1500, 600), (1000, 1000), (17, 23)):
        got = fit_cover(Image.new("RGB", (w, h)), 256)
        assert got.size == (256, 256)


def test_non_square_photo_still_fills_the_whole_circle(tmp_path, portrait_photo_path):
    """A tall photo must not leave bars at the sides of the badge."""
    path, _ = _make(tmp_path, portrait_photo_path)
    with Image.open(path) as img:
        rgba = img.convert("RGBA")
        cy = rgba.height // 2
        assert rgba.getpixel((3, cy))[3] > 200
        assert rgba.getpixel((rgba.width - 4, cy))[3] > 200


# --------------------------------------------------------------------------
# Offset clamping
# --------------------------------------------------------------------------


def test_square_photo_at_scale_1_cannot_pan():
    """At cover-fit there is no slack, so any pan would expose background."""
    assert clamp_offsets(0.9, -0.9, 1.0, 1000, 1000) == (0.0, 0.0)


def test_zooming_in_creates_pan_room():
    x, y = clamp_offsets(10.0, -10.0, 2.0, 1000, 1000)
    assert x == pytest.approx(0.5)  # (2.0 - 1) / 2
    assert y == pytest.approx(-0.5)


def test_tall_photo_can_pan_vertically_at_scale_1():
    """A 600x1500 photo cover-fitted to a square has vertical slack to spare."""
    x, y = clamp_offsets(5.0, 5.0, 1.0, 600, 1500)
    assert x == pytest.approx(0.0)
    assert y == pytest.approx(((1500 / 600) - 1) / 2)


def test_offsets_within_range_are_untouched():
    assert clamp_offsets(0.1, -0.2, 2.0, 1000, 1000) == (0.1, -0.2)


def test_render_reports_the_clamped_crop_back(tmp_path, photo_path):
    """The client must learn the crop actually used, not the one it asked for."""
    _, info = _make(tmp_path, photo_path, offset_x=99.0, scale=1.0)
    assert info["crop"]["offset_x"] == 0.0


def test_scale_below_one_is_raised_to_one(tmp_path, photo_path):
    _, info = _make(tmp_path, photo_path, scale=0.2)
    assert info["crop"]["scale"] == 1.0


# --------------------------------------------------------------------------
# Panning actually moves the image
# --------------------------------------------------------------------------


def test_offset_shifts_content_by_the_expected_pixels(tmp_path):
    """A half-diameter offset at 2x zoom must move content by exactly that."""
    src = tmp_path / "split.png"
    img = Image.new("RGB", (1000, 1000), (255, 0, 0))
    # Right half blue, so we can see which half lands in the middle.
    img.paste(Image.new("RGB", (500, 1000), (0, 0, 255)), (500, 0))
    img.save(src)

    centre = mm_to_px(58.0) // 2

    neutral, _ = _make(tmp_path, str(src), scale=2.0, offset_x=0.0)
    with Image.open(neutral) as out:
        px = out.convert("RGB").getpixel((centre, centre))
    # The seam sits dead centre; sample just left of it to get red.
    with Image.open(neutral) as out:
        left_px = out.convert("RGB").getpixel((centre - 20, centre))
        right_px = out.convert("RGB").getpixel((centre + 20, centre))
    assert left_px[0] > 200 and right_px[2] > 200

    # Pan right by a quarter diameter: the seam moves right, so the centre
    # should now be red (the left half of the photo).
    shifted, _ = _make(tmp_path, str(src), scale=2.0, offset_x=0.25)
    with Image.open(shifted) as out:
        px = out.convert("RGB").getpixel((centre, centre))
    assert px[0] > 200, f"expected red at centre after panning, got {px}"


# --------------------------------------------------------------------------
# Templates
# --------------------------------------------------------------------------


def test_template_is_clipped_to_the_circle(tmp_path, photo_path):
    """Template corners must not print outside the badge."""
    tpl = tmp_path / "square.png"
    Image.new("RGBA", (1000, 1000), (0, 255, 0, 255)).save(tpl)
    path, _ = _make(tmp_path, photo_path, template=str(tpl))
    with Image.open(path) as img:
        rgba = img.convert("RGBA")
        assert rgba.getpixel((1, 1))[3] == 0
        assert rgba.getpixel((rgba.width // 2, rgba.height // 2))[3] == 255


def test_non_square_template_is_covered_not_stretched(tmp_path, photo_path):
    """A 2:1 template must be centre-cropped, matching the preview's object-fit."""
    tpl = tmp_path / "wide.png"
    img = Image.new("RGBA", (1000, 500), (0, 0, 0, 0))
    # Opaque left third; after cover-crop the visible window is the middle 500px.
    img.paste(Image.new("RGBA", (250, 500), (255, 0, 255, 255)), (0, 0))
    img.save(tpl)
    path, _ = _make(tmp_path, photo_path, template=str(tpl))
    with Image.open(path) as out:
        assert out.size == (mm_to_px(58.0), mm_to_px(58.0))


def test_missing_template_still_renders_the_photo(tmp_path, photo_path):
    path, info = _make(tmp_path, photo_path, template=str(tmp_path / "nope.png"))
    assert info["badge_px"] == mm_to_px(58.0)
    with Image.open(path) as img:
        assert img.size == (mm_to_px(58.0), mm_to_px(58.0))


# --------------------------------------------------------------------------
# Failure handling
# --------------------------------------------------------------------------


def test_unreadable_photo_raises_a_clear_error(tmp_path):
    bad = tmp_path / "bad.png"
    bad.write_bytes(b"this is definitely not a png")
    with pytest.raises(CompositeError, match="Could not read image"):
        _make(tmp_path, str(bad))


def test_exif_rotation_is_applied(tmp_path):
    """
    Phone cameras store the sensor image unrotated plus an EXIF orientation
    tag. Ignoring the tag prints every portrait photo on its side.
    """
    src = tmp_path / "rotated.jpg"
    # Landscape buffer: left half red, right half blue.
    img = Image.new("RGB", (1000, 500), (255, 0, 0))
    img.paste(Image.new("RGB", (500, 500), (0, 0, 255)), (500, 0))
    exif = img.getexif()
    exif[274] = 6  # orientation: rotate 90 CW on display
    img.save(src, "JPEG", exif=exif, quality=95)

    from app.services.compositor import open_image

    opened = open_image(str(src))
    # After transposition the 1000x500 landscape becomes 500x1000 portrait.
    assert opened.size == (500, 1000), f"EXIF orientation not applied: {opened.size}"

    # The originally-left red half must now be at the top.
    top = opened.convert("RGB").getpixel((250, 100))
    bottom = opened.convert("RGB").getpixel((250, 900))
    assert top[0] > 200, f"expected red at top, got {top}"
    assert bottom[2] > 200, f"expected blue at bottom, got {bottom}"
