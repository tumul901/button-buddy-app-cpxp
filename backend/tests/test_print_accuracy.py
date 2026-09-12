"""
Print accuracy — the guarantee the whole product rests on.

These tests read the generated PDF back and measure it, rather than trusting
the code that wrote it. A badge must be exactly `diameter_mm` on paper.
"""

import os

import pypdf
import pytest
from pypdf.generic import ContentStream

from app.services.compositor import composite_badge
from app.services.layout import compute_layout
from app.services.pdf_exporter import export_pdf
from app.services.units import mm_to_px, px_to_mm

MM_PER_PT = 25.4 / 72.0
# 0.05 mm is well inside what any ruler or badge press can resolve.
TOL_MM = 0.05


def _page_size_mm(page) -> tuple[float, float]:
    box = page.mediabox
    return (float(box.width) * MM_PER_PT, float(box.height) * MM_PER_PT)


def _image_placements_mm(page) -> list[tuple[float, float, float, float]]:
    """
    Extract (x, y, width, height) in mm for every image drawn on the page.

    An image is always painted by `cm` (set the transform) followed by `Do`
    (paint the XObject), and ReportLab emits a pure scale+translate matrix, so
    the matrix diagonal *is* the on-paper size in points.
    """
    placements = []
    ctm = None
    for operands, operator in ContentStream(page.get_contents(), None).operations:
        if operator == b"cm":
            ctm = [float(o) for o in operands]
        elif operator == b"Do" and ctm is not None:
            a, b, c, d, e, f = ctm
            placements.append((e * MM_PER_PT, f * MM_PER_PT, a * MM_PER_PT, d * MM_PER_PT))
    return placements


@pytest.fixture
def composite(tmp_path, photo_path, template_path):
    def _make(diameter_mm=58.0, bleed_mm=0.0):
        out = tmp_path / f"badge_{diameter_mm}_{bleed_mm}.png"
        info = composite_badge(
            photo_path=photo_path,
            template_path=template_path,
            diameter_mm=diameter_mm,
            bleed_mm=bleed_mm,
            crop_offset_x=0.0,
            crop_offset_y=0.0,
            crop_scale=1.0,
            output_path=str(out),
        )
        return str(out), info

    return _make


# --------------------------------------------------------------------------
# Unit conversion
# --------------------------------------------------------------------------


def test_mm_to_px_reference_values():
    assert mm_to_px(58) == 685  # the canonical badge
    assert mm_to_px(25.4) == 300  # exactly one inch at 300 DPI
    assert mm_to_px(0) == 0


def test_px_to_mm_roundtrip():
    for mm_val in (25.0, 37.0, 58.0, 75.0, 100.0):
        assert abs(px_to_mm(mm_to_px(mm_val)) - mm_val) < 0.05


# --------------------------------------------------------------------------
# Composite geometry
# --------------------------------------------------------------------------


@pytest.mark.parametrize("diameter", [25.0, 32.0, 38.0, 45.0, 58.0, 75.0, 100.0])
def test_composite_is_exactly_badge_px_square(composite, diameter):
    from PIL import Image

    path, info = composite(diameter_mm=diameter)
    with Image.open(path) as img:
        assert img.size == (mm_to_px(diameter), mm_to_px(diameter))
        # PNG stores resolution as integer pixels-per-metre, so 300 DPI
        # round-trips as 299.9994. That is 0.0002% - far below any ruler.
        dpi_x, dpi_y = img.info.get("dpi")
        assert dpi_x == pytest.approx(300, abs=0.01)
        assert dpi_y == pytest.approx(300, abs=0.01)
    assert info["badge_px"] == mm_to_px(diameter)


def test_composite_with_bleed_adds_bleed_on_both_sides(composite):
    from PIL import Image

    path, info = composite(diameter_mm=58.0, bleed_mm=3.0)
    expected = mm_to_px(58.0) + 2 * mm_to_px(3.0)
    with Image.open(path) as img:
        assert img.size == (expected, expected)
    assert info["total_px"] == expected
    assert info["total_diameter_mm"] == pytest.approx(64.0)


def test_composite_corners_are_transparent(composite):
    """The badge is a circle: corners must carry no ink."""
    from PIL import Image

    path, _ = composite(diameter_mm=58.0)
    with Image.open(path) as img:
        rgba = img.convert("RGBA")
        for xy in ((1, 1), (rgba.width - 2, 1), (1, rgba.height - 2), (rgba.width - 2, rgba.height - 2)):
            assert rgba.getpixel(xy)[3] == 0, f"corner {xy} is not transparent"
        assert rgba.getpixel((rgba.width // 2, rgba.height // 2))[3] == 255


def test_composite_fills_circle_edge_to_edge(composite):
    """No white sliver just inside the rim — a common cover-fit off-by-one."""
    from PIL import Image

    path, _ = composite(diameter_mm=58.0)
    with Image.open(path) as img:
        rgba = img.convert("RGBA")
        cy = rgba.height // 2
        # 2 px inside the left and right extremes of the circle
        assert rgba.getpixel((2, cy))[3] > 200
        assert rgba.getpixel((rgba.width - 3, cy))[3] > 200


# --------------------------------------------------------------------------
# PDF: the accurate print path
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "paper,orientation,w_mm,h_mm",
    [
        ("A4", "portrait", 210.0, 297.0),
        ("A4", "landscape", 297.0, 210.0),
        ("A3", "portrait", 297.0, 420.0),
        ("Letter", "portrait", 215.9, 279.4),
        ("Legal", "portrait", 215.9, 355.6),
        ("4x6", "portrait", 101.6, 152.4),
    ],
)
def test_pdf_page_size_is_exact(tmp_path, composite, paper, orientation, w_mm, h_mm):
    path, _ = composite(diameter_mm=38.0)
    out = tmp_path / "sheet.pdf"
    export_pdf(
        output_path=str(out),
        paper=paper,
        orientation=orientation,
        diameter_mm=38.0,
        bleed_mm=0.0,
        gap_mm=5.0,
        margin_mm=10.0,
        badge_images=[path],
    )
    reader = pypdf.PdfReader(str(out))
    got_w, got_h = _page_size_mm(reader.pages[0])
    assert got_w == pytest.approx(w_mm, abs=TOL_MM)
    assert got_h == pytest.approx(h_mm, abs=TOL_MM)


@pytest.mark.parametrize("diameter", [25.0, 38.0, 58.0, 75.0])
def test_pdf_badge_is_drawn_at_exact_physical_size(tmp_path, composite, diameter):
    """The whole point: measure the badge inside the PDF, in mm."""
    path, _ = composite(diameter_mm=diameter)
    out = tmp_path / "sheet.pdf"
    export_pdf(
        output_path=str(out),
        paper="A4",
        orientation="portrait",
        diameter_mm=diameter,
        bleed_mm=0.0,
        gap_mm=5.0,
        margin_mm=10.0,
        badge_images=[path],
        copies=1,
    )
    reader = pypdf.PdfReader(str(out))
    placements = _image_placements_mm(reader.pages[0])
    assert placements, "no image was drawn into the PDF"
    x, y, w, h = placements[0]
    assert w == pytest.approx(diameter, abs=TOL_MM), f"width {w} mm != {diameter} mm"
    assert h == pytest.approx(diameter, abs=TOL_MM), f"height {h} mm != {diameter} mm"


def test_pdf_badge_with_bleed_occupies_full_footprint(tmp_path, composite):
    path, _ = composite(diameter_mm=58.0, bleed_mm=3.0)
    out = tmp_path / "sheet.pdf"
    export_pdf(
        output_path=str(out),
        paper="A4",
        orientation="portrait",
        diameter_mm=58.0,
        bleed_mm=3.0,
        gap_mm=5.0,
        margin_mm=10.0,
        badge_images=[path],
        copies=1,
    )
    reader = pypdf.PdfReader(str(out))
    _, _, w, h = _image_placements_mm(reader.pages[0])[0]
    # Artwork spans trim + bleed on both sides; the trim circle stays 58 mm.
    assert w == pytest.approx(64.0, abs=TOL_MM)
    assert h == pytest.approx(64.0, abs=TOL_MM)


def test_every_badge_on_the_sheet_is_the_same_exact_size(tmp_path, composite):
    path, _ = composite(diameter_mm=58.0)
    out = tmp_path / "sheet.pdf"
    result = export_pdf(
        output_path=str(out),
        paper="A4",
        orientation="portrait",
        diameter_mm=58.0,
        bleed_mm=0.0,
        gap_mm=5.0,
        margin_mm=10.0,
        badge_images=[path],
        copies=None,  # fill the page
    )
    reader = pypdf.PdfReader(str(out))
    placements = _image_placements_mm(reader.pages[0])
    assert len(placements) == result["layout"]["capacity_per_page"] == 12
    for _, _, w, h in placements:
        assert w == pytest.approx(58.0, abs=TOL_MM)
        assert h == pytest.approx(58.0, abs=TOL_MM)


def test_no_badge_is_placed_outside_the_page(tmp_path, composite):
    """Nothing may run off the sheet or into the ruler band."""
    path, _ = composite(diameter_mm=58.0)
    out = tmp_path / "sheet.pdf"
    export_pdf(
        output_path=str(out),
        paper="A4",
        orientation="portrait",
        diameter_mm=58.0,
        bleed_mm=0.0,
        gap_mm=5.0,
        margin_mm=10.0,
        badge_images=[path],
        copies=None,
    )
    reader = pypdf.PdfReader(str(out))
    page = reader.pages[0]
    pw, ph = _page_size_mm(page)
    for x, y, w, h in _image_placements_mm(page):
        assert x >= -TOL_MM, f"badge starts off the left edge at {x} mm"
        assert y >= -TOL_MM, f"badge starts below the bottom edge at {y} mm"
        assert x + w <= pw + TOL_MM, f"badge ends at {x + w} mm past {pw} mm page"
        assert y + h <= ph + TOL_MM, f"badge ends at {y + h} mm past {ph} mm page"


def test_ruler_band_is_not_overlapped_by_badges(tmp_path, composite):
    """
    v1 drew the calibration ruler over the grid, so at margins below 10 mm the
    ruler labels printed on top of the first row of badges.
    """
    from app.config import RULER_BAND_MM

    path, _ = composite(diameter_mm=58.0)
    for margin in (0.0, 5.0, 8.0, 10.0, 15.0):
        out = tmp_path / f"sheet_{margin}.pdf"
        export_pdf(
            output_path=str(out),
            paper="A4",
            orientation="portrait",
            diameter_mm=58.0,
            bleed_mm=0.0,
            gap_mm=5.0,
            margin_mm=margin,
            badge_images=[path],
            copies=None,
            include_ruler=True,
        )
        reader = pypdf.PdfReader(str(out))
        page = reader.pages[0]
        _, ph = _page_size_mm(page)
        band_bottom_from_top = margin + RULER_BAND_MM
        for _, y, _, h in _image_placements_mm(page):
            top_from_top = ph - (y + h)
            assert top_from_top >= band_bottom_from_top - TOL_MM, (
                f"margin={margin}: badge top at {top_from_top:.2f} mm intrudes into "
                f"the ruler band ending at {band_bottom_from_top:.2f} mm"
            )


def test_pagination_spills_to_more_pages(tmp_path, composite):
    path, _ = composite(diameter_mm=58.0)
    out = tmp_path / "sheet.pdf"
    result = export_pdf(
        output_path=str(out),
        paper="A4",
        orientation="portrait",
        diameter_mm=58.0,
        bleed_mm=0.0,
        gap_mm=5.0,
        margin_mm=10.0,
        badge_images=[path],
        copies=30,  # 12 per page -> 3 pages
    )
    reader = pypdf.PdfReader(str(out))
    assert result["total_pages"] == 3
    assert len(reader.pages) == 3
    assert result["badges_placed"] == 30
    assert len(_image_placements_mm(reader.pages[2])) == 6  # 30 - 24


def test_export_refuses_a_badge_that_cannot_fit(tmp_path, composite):
    path, _ = composite(diameter_mm=100.0)
    with pytest.raises(ValueError, match="does not fit"):
        export_pdf(
            output_path=str(tmp_path / "x.pdf"),
            paper="4x6",
            orientation="portrait",
            diameter_mm=100.0,
            bleed_mm=0.0,
            gap_mm=5.0,
            margin_mm=10.0,
            badge_images=[path],
        )


# --------------------------------------------------------------------------
# Cutter / perforation ring
# --------------------------------------------------------------------------


def _dashed_ring_sizes_mm(page) -> list[tuple[float, float]]:
    """Bounding boxes of every DASHED path — the cutter rings."""
    dash_on = False
    rings = []
    current: list[tuple[float, float]] = []
    has_curve = False
    for operands, op in ContentStream(page.get_contents(), None).operations:
        if op == b"d":
            pattern = operands[0]
            dash_on = bool(pattern and len(list(pattern)) > 0)
        elif op == b"m":
            current = [(float(operands[0]), float(operands[1]))]
            has_curve = False
        elif op == b"l" and current:
            current.append((float(operands[0]), float(operands[1])))
        elif op == b"c" and current:
            current.append((float(operands[4]), float(operands[5])))
            has_curve = True
        elif op in (b"S", b"s"):
            # Only bezier paths are rings; the dashed straight lines are the
            # full-height tangent feed guides, which are measured separately.
            if dash_on and current and has_curve:
                xs = [p[0] for p in current]
                ys = [p[1] for p in current]
                rings.append(
                    ((max(xs) - min(xs)) * MM_PER_PT, (max(ys) - min(ys)) * MM_PER_PT)
                )
            current = []
            has_curve = False
    return rings


@pytest.mark.parametrize("perforation", [8.0, 12.0, 20.0])
def test_cutter_ring_is_badge_plus_perforation(tmp_path, composite, perforation):
    """The dashed ring is what the press cuts, so its size must be exact."""
    path, _ = composite(diameter_mm=58.0)
    out = tmp_path / "sheet.pdf"
    export_pdf(
        output_path=str(out),
        paper="A4",
        orientation="portrait",
        diameter_mm=58.0,
        bleed_mm=0.0,
        gap_mm=5.0,
        margin_mm=10.0,
        badge_images=[path],
        copies=None,
        perforation_mm=perforation,
    )
    rings = _dashed_ring_sizes_mm(pypdf.PdfReader(str(out)).pages[0])
    assert rings, "no dashed cutter ring was drawn"
    expected = 58.0 + perforation
    for w, h in rings:
        assert w == pytest.approx(expected, abs=TOL_MM)
        assert h == pytest.approx(expected, abs=TOL_MM)


def test_cutter_ring_off_by_default_draws_nothing(tmp_path, composite):
    path, _ = composite(diameter_mm=58.0)
    out = tmp_path / "sheet.pdf"
    export_pdf(
        output_path=str(out),
        paper="A4",
        orientation="portrait",
        diameter_mm=58.0,
        bleed_mm=0.0,
        gap_mm=5.0,
        margin_mm=10.0,
        badge_images=[path],
        perforation_mm=0.0,
    )
    assert _dashed_ring_sizes_mm(pypdf.PdfReader(str(out)).pages[0]) == []


def test_cutter_rings_never_overlap_or_leave_the_page(tmp_path, composite):
    """
    The layout cell must grow to hold the ring. Sizing cells to the artwork
    alone would let neighbouring rings intersect and run off the sheet.
    """
    path, _ = composite(diameter_mm=58.0)
    out = tmp_path / "sheet.pdf"
    result = export_pdf(
        output_path=str(out),
        paper="A4",
        orientation="portrait",
        diameter_mm=58.0,
        bleed_mm=0.0,
        gap_mm=5.0,
        margin_mm=10.0,
        badge_images=[path],
        copies=None,
        perforation_mm=12.0,
    )
    # 70 mm cells, not 58 mm ones.
    assert result["layout"]["badge_diameter_mm"] == pytest.approx(70.0)
    assert result["layout"]["capacity_per_page"] == 6

    page = pypdf.PdfReader(str(out)).pages[0]
    pw, ph = _page_size_mm(page)

    # Centres are the badge placements; rings are concentric with them.
    centres = [(x + w / 2, y + h / 2) for x, y, w, h in _image_placements_mm(page)]
    ring_r = (58.0 + 12.0) / 2

    for cx, cy in centres:
        assert cx - ring_r >= -TOL_MM and cx + ring_r <= pw + TOL_MM
        assert cy - ring_r >= -TOL_MM and cy + ring_r <= ph + TOL_MM

    for i, a in enumerate(centres):
        for b in centres[i + 1 :]:
            d = ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5
            assert d >= 2 * ring_r - TOL_MM, f"cutter rings overlap: centres {d:.2f} mm apart"


def _dashed_vertical_lines_mm(page) -> list[float]:
    """X positions (mm) of full-height dashed straight lines — the feed guides."""
    dash_on = False
    xs: list[float] = []
    start = None
    pts: list[tuple[float, float]] = []
    for operands, op in ContentStream(page.get_contents(), None).operations:
        if op == b"d":
            pattern = operands[0]
            dash_on = bool(pattern and len(list(pattern)) > 0)
        elif op == b"m":
            start = (float(operands[0]), float(operands[1]))
            pts = [start]
        elif op == b"l" and start is not None:
            pts.append((float(operands[0]), float(operands[1])))
        elif op == b"c":
            start = None  # a curve: this is a ring, not a guide
        elif op in (b"S", b"s"):
            if dash_on and start is not None and len(pts) == 2:
                (x0, y0), (x1, y1) = pts[0], pts[1]
                if abs(x0 - x1) < 1e-6 and abs(y1 - y0) > 1:  # vertical
                    xs.append(x0 * MM_PER_PT)
            start = None
            pts = []
    return sorted(xs)


def test_tangent_guides_touch_the_cutter_rings(tmp_path, composite):
    """
    The dashed guides must be exactly tangent to the rings: the operator
    aligns the sheet against them in the cutter, so a guide that is merely
    near the ring is worse than none at all.
    """
    path, _ = composite(diameter_mm=58.0)
    out = tmp_path / "sheet.pdf"
    export_pdf(
        output_path=str(out),
        paper="A4",
        orientation="portrait",
        diameter_mm=58.0,
        bleed_mm=0.0,
        gap_mm=5.0,
        margin_mm=10.0,
        badge_images=[path],
        copies=None,
        perforation_mm=12.0,
    )
    page = pypdf.PdfReader(str(out)).pages[0]
    guides = _dashed_vertical_lines_mm(page)
    assert guides, "no tangent feed guides were drawn"

    ring_r = (58.0 + 12.0) / 2
    centres = sorted(
        {round(x + w / 2, 3) for x, _, w, _ in _image_placements_mm(page)}
    )
    expected = sorted([c - ring_r for c in centres] + [c + ring_r for c in centres])

    # Touching rings share a guide, so compare as a deduplicated set.
    def dedupe(vals):
        out = []
        for v in sorted(vals):
            if not out or abs(v - out[-1]) > 0.2:
                out.append(v)
        return out

    expected = dedupe(expected)
    assert len(guides) == len(expected), f"expected {len(expected)} guides, got {len(guides)}"
    for got, want in zip(guides, expected):
        assert got == pytest.approx(want, abs=TOL_MM), f"guide at {got} mm, ring edge at {want} mm"


def test_tangent_guides_span_the_full_page_height(tmp_path, composite):
    path, _ = composite(diameter_mm=58.0)
    out = tmp_path / "sheet.pdf"
    export_pdf(
        output_path=str(out),
        paper="4x6",
        orientation="portrait",
        diameter_mm=58.0,
        bleed_mm=0.0,
        gap_mm=2.0,
        margin_mm=5.0,
        badge_images=[path],
        copies=None,
        perforation_mm=12.0,
        include_ruler=False,
    )
    page = pypdf.PdfReader(str(out)).pages[0]
    _, ph = _page_size_mm(page)

    spans = []
    dash_on = False
    pts: list[tuple[float, float]] = []
    started = False
    for operands, op in ContentStream(page.get_contents(), None).operations:
        if op == b"d":
            pattern = operands[0]
            dash_on = bool(pattern and len(list(pattern)) > 0)
        elif op == b"m":
            pts = [(float(operands[0]), float(operands[1]))]
            started = True
        elif op == b"l" and started:
            pts.append((float(operands[0]), float(operands[1])))
        elif op == b"c":
            started = False
        elif op in (b"S", b"s"):
            if dash_on and started and len(pts) == 2 and abs(pts[0][0] - pts[1][0]) < 1e-6:
                spans.append(abs(pts[1][1] - pts[0][1]) * MM_PER_PT)
            started = False
            pts = []

    assert spans, "no vertical guides found"
    for span in spans:
        assert span == pytest.approx(ph, abs=TOL_MM), f"guide spans {span} mm of a {ph} mm page"


def test_no_tangent_guides_when_the_ring_is_off(tmp_path, composite):
    path, _ = composite(diameter_mm=58.0)
    out = tmp_path / "sheet.pdf"
    export_pdf(
        output_path=str(out),
        paper="A4",
        orientation="portrait",
        diameter_mm=58.0,
        bleed_mm=0.0,
        gap_mm=5.0,
        margin_mm=10.0,
        badge_images=[path],
        perforation_mm=0.0,
    )
    assert _dashed_vertical_lines_mm(pypdf.PdfReader(str(out)).pages[0]) == []


def _dashed_horizontal_lines_mm(page, page_h_mm: float) -> list[float]:
    """Y positions (mm from the top) of dashed horizontal guides."""
    dash_on = False
    ys: list[float] = []
    pts: list[tuple[float, float]] = []
    started = False
    for operands, op in ContentStream(page.get_contents(), None).operations:
        if op == b"d":
            pattern = operands[0]
            dash_on = bool(pattern and len(list(pattern)) > 0)
        elif op == b"m":
            pts = [(float(operands[0]), float(operands[1]))]
            started = True
        elif op == b"l" and started:
            pts.append((float(operands[0]), float(operands[1])))
        elif op == b"c":
            started = False
        elif op in (b"S", b"s"):
            if dash_on and started and len(pts) == 2:
                (x0, y0), (x1, y1) = pts
                if abs(y0 - y1) < 1e-6 and abs(x1 - x0) > 1:
                    ys.append(page_h_mm - y0 * MM_PER_PT)
            started = False
            pts = []
    return sorted(ys)


def test_cut_guides_follow_the_layout_in_both_orientations(tmp_path, composite):
    """
    Guides are emitted on both axes, so a row of badges gets horizontal cut
    lines just as a column gets vertical ones. Only emitting verticals is
    correct for stacked badges and wrong for side-by-side ones.
    """
    path, _ = composite(diameter_mm=58.0)
    ring = 58.0 + 12.0

    for orientation, expect_cols, expect_rows in (("portrait", 1, 2), ("landscape", 2, 1)):
        out = tmp_path / f"sheet_{orientation}.pdf"
        result = export_pdf(
            output_path=str(out),
            paper="4x6",
            orientation=orientation,
            diameter_mm=58.0,
            bleed_mm=0.0,
            gap_mm=2.0,
            margin_mm=5.0,
            badge_images=[path],
            copies=None,
            perforation_mm=12.0,
            include_ruler=False,
        )
        layout = result["layout"]
        assert (layout["cols"], layout["rows"]) == (expect_cols, expect_rows)

        page = pypdf.PdfReader(str(out)).pages[0]
        _, ph = _page_size_mm(page)
        verticals = _dashed_vertical_lines_mm(page)
        horizontals = _dashed_horizontal_lines_mm(page, ph)

        assert verticals, f"{orientation}: no vertical cut guides"
        assert horizontals, f"{orientation}: no horizontal cut guides"

        # Every badge must be bracketed on both axes by tangent guides.
        for x, y, w, h in _image_placements_mm(page):
            cx, cy_top = x + w / 2, ph - (y + h / 2)
            assert any(abs(v - (cx - ring / 2)) < TOL_MM for v in verticals)
            assert any(abs(v - (cx + ring / 2)) < TOL_MM for v in verticals)
            assert any(abs(hh - (cy_top - ring / 2)) < TOL_MM for hh in horizontals)
            assert any(abs(hh - (cy_top + ring / 2)) < TOL_MM for hh in horizontals)
