"""
Sheet layout.

The capacity formula and the frontend mirror of it are both pinned here: the
two implementations will drift otherwise, and a mismatch means the preview
lies about how many badges the user is about to get.
"""

import json
import os
import subprocess

import pytest

from app.services.layout import PAPER_SIZES_MM, compute_layout, fit_count

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
FRONTEND_LAYOUT_TS = os.path.join(REPO_ROOT, "frontend", "src", "utils", "paperLayouts.ts")


# --------------------------------------------------------------------------
# The capacity formula
# --------------------------------------------------------------------------


def test_fit_count_accounts_for_gaps_between_only():
    # 3 badges of 58 with 5 gaps: 58*3 + 5*2 = 184 <= 190
    assert fit_count(190, 58, 5) == 3
    # exactly flush
    assert fit_count(184, 58, 5) == 3
    # one millimetre short
    assert fit_count(183, 58, 5) == 2
    # a single badge needs no gap at all
    assert fit_count(58, 58, 5) == 1
    assert fit_count(57.9, 58, 5) == 0


@pytest.mark.parametrize(
    "paper,gap,expected",
    [
        # The naive floor(usable/(d+gap)) undercounts these badly.
        ("Letter", 10.0, 9),  # v1 said 6
        ("A3", 10.0, 24),  # v1 said 20
        ("4x6", 10.0, 2),  # v1 said 1
        ("A4", 5.0, 12),  # unchanged - the default that hid the bug
    ],
)
def test_capacity_does_not_waste_a_trailing_gap(paper, gap, expected):
    layout = compute_layout(paper, 58.0, gap, 10.0, "portrait")
    assert layout["capacity_per_page"] == expected


def test_a4_58mm_matches_the_documented_reference():
    layout = compute_layout("A4", 58.0, 5.0, 10.0, "portrait")
    assert (layout["cols"], layout["rows"], layout["capacity_per_page"]) == (3, 4, 12)


# --------------------------------------------------------------------------
# Refusing impossible layouts
# --------------------------------------------------------------------------


def test_oversized_badge_reports_it_does_not_fit():
    layout = compute_layout("4x6", 100.0, 5.0, 10.0, "portrait")
    assert layout["fits"] is False
    assert layout["capacity_per_page"] == 0
    assert "does not fit" in layout["reason"]
    assert "100.0 mm" in layout["reason"]


def test_a_badge_exactly_the_usable_width_still_fits():
    # 4x6 portrait is 101.6 wide; with 10 mm margins that is 81.6 usable.
    assert compute_layout("4x6", 81.6, 5.0, 10.0, "portrait")["cols"] == 1
    assert compute_layout("4x6", 81.7, 5.0, 10.0, "portrait")["fits"] is False


def test_badges_never_exceed_the_usable_area():
    """Whatever the inputs, the grid must physically fit inside the margins."""
    for paper in PAPER_SIZES_MM:
        for orientation in ("portrait", "landscape"):
            for diameter in (25.0, 38.0, 58.0, 75.0, 100.0):
                for gap in (0.0, 5.0, 12.0):
                    for margin in (0.0, 5.0, 10.0, 25.0):
                        lo = compute_layout(
                            paper, diameter, gap, margin, orientation, reserve_top_mm=12.0
                        )
                        if not lo["fits"]:
                            continue
                        used_w = lo["cols"] * diameter + (lo["cols"] - 1) * gap
                        used_h = lo["rows"] * diameter + (lo["rows"] - 1) * gap
                        assert used_w <= lo["paper_mm"]["w"] - 2 * margin + 1e-6
                        assert used_h <= lo["paper_mm"]["h"] - 2 * margin - 12.0 + 1e-6


def test_ruler_band_reduces_rows_not_overlaps_them():
    without = compute_layout("A4", 58.0, 5.0, 10.0, "portrait", reserve_top_mm=0.0)
    with_band = compute_layout("A4", 58.0, 5.0, 10.0, "portrait", reserve_top_mm=12.0)
    assert with_band["rows"] <= without["rows"]
    assert with_band["origin_mm"]["y"] == pytest.approx(22.0)


# --------------------------------------------------------------------------
# Positions
# --------------------------------------------------------------------------


def test_orientation_swaps_dimensions():
    portrait = compute_layout("A4", 58.0, 5.0, 10.0, "portrait")
    landscape = compute_layout("A4", 58.0, 5.0, 10.0, "landscape")
    assert (portrait["paper_mm"]["w"], portrait["paper_mm"]["h"]) == (210.0, 297.0)
    assert (landscape["paper_mm"]["w"], landscape["paper_mm"]["h"]) == (297.0, 210.0)


def test_paper_aliases_normalise():
    assert compute_layout("4x6in", 38.0, 5.0, 10.0)["paper"] == "4x6"


def test_unknown_paper_is_rejected():
    with pytest.raises(ValueError, match="Unknown paper size"):
        compute_layout("A7", 38.0, 5.0, 10.0)


def test_pages_is_ceiling_of_requested_over_capacity():
    lo = compute_layout("A4", 58.0, 5.0, 10.0, "portrait", copies=30, reserve_top_mm=12.0)
    assert lo["capacity_per_page"] == 12
    assert lo["pages"] == 3


# --------------------------------------------------------------------------
# Parity with the frontend mirror
# --------------------------------------------------------------------------


def _tool(name: str):
    """Locate a node tool in the frontend's node_modules/.bin."""
    base = os.path.join(REPO_ROOT, "frontend", "node_modules", ".bin")
    for candidate in (f"{name}.cmd", name):
        path = os.path.join(base, candidate)
        if os.path.exists(path):
            return path
    return None


def _node_available() -> bool:
    try:
        subprocess.run(["node", "--version"], capture_output=True, timeout=20, check=True)
        return True
    except Exception:
        return False


HARNESS_LINES = [
    "import { computeLayout } from './paperLayouts.js';",
    "const cases = __CASES__;",
    "const out = cases.map(([p,o,d,g,m]) => {",
    "  const l = computeLayout(p,o,d,g,m,undefined,12);",
    "  return [l.cols, l.rows, l.fits];",
    "});",
    "console.log(JSON.stringify(out));",
]


@pytest.mark.skipif(not _node_available(), reason="node is not available")
@pytest.mark.skipif(_tool("tsc") is None, reason="tsc not installed (run npm install)")
@pytest.mark.skipif(
    not os.path.exists(FRONTEND_LAYOUT_TS), reason="frontend layout module not found"
)
def test_frontend_layout_matches_backend(tmp_path):
    """
    Compile the real TypeScript mirror, run it over a matrix of inputs, and
    require identical cols/rows/fits. These are two implementations of one
    contract; if they disagree, the preview lies about what will print.
    """
    subprocess.run(
        [
            _tool("tsc"),
            FRONTEND_LAYOUT_TS,
            "--outDir",
            str(tmp_path),
            "--target",
            "es2022",
            "--module",
            "esnext",
            "--moduleResolution",
            "bundler",
            "--skipLibCheck",
        ],
        capture_output=True,
        text=True,
        timeout=180,
    )
    compiled = tmp_path / "paperLayouts.js"
    assert compiled.exists(), "tsc produced no output"

    cases = []
    for paper in ("A4", "A3", "Letter", "Legal", "4x6"):
        for orientation in ("portrait", "landscape"):
            for diameter in (25.0, 38.0, 58.0, 75.0, 100.0):
                for gap in (0.0, 5.0, 10.0):
                    for margin in (0.0, 10.0, 25.0):
                        cases.append([paper, orientation, diameter, gap, margin])

    harness = tmp_path / "harness.mjs"
    body = os.linesep.join(HARNESS_LINES).replace("__CASES__", json.dumps(cases))
    harness.write_text(body, encoding="utf-8")

    proc = subprocess.run(["node", str(harness)], capture_output=True, text=True, timeout=60)
    assert proc.returncode == 0, "node failed: " + proc.stderr
    got = json.loads(proc.stdout.strip().splitlines()[-1])

    mismatches = []
    for (paper, orientation, diameter, gap, margin), (cols, rows, fits) in zip(cases, got):
        exp = compute_layout(paper, diameter, gap, margin, orientation, reserve_top_mm=12.0)
        if (exp["cols"], exp["rows"], exp["fits"]) != (cols, rows, bool(fits)):
            mismatches.append(
                f"{paper} {orientation} d={diameter} gap={gap} margin={margin}: "
                f"py=({exp['cols']},{exp['rows']},{exp['fits']}) ts=({cols},{rows},{fits})"
            )
    assert not mismatches, f"{len(mismatches)}/{len(cases)} layout cases disagree: " + "; ".join(
        mismatches[:15]
    )
