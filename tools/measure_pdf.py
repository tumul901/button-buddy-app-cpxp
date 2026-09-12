"""
Measure image placements in a PDF by composing the full graphics-state stack.

ReportLab emits a flat `cm` per image, but Chrome nests `q`/`cm`/`Q`, so the
last `cm` alone is meaningless — the on-paper size is the product of every
enclosing transform. This walks the stack the way a PDF renderer does.
"""

import sys

import pypdf
from pypdf.generic import ContentStream

MM_PER_PT = 25.4 / 72.0
IDENTITY = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)


def mul(m, n):
    """Matrix product for PDF's [a b c d e f] row-vector convention."""
    a1, b1, c1, d1, e1, f1 = m
    a2, b2, c2, d2, e2, f2 = n
    return (
        a1 * a2 + b1 * c2,
        a1 * b2 + b1 * d2,
        c1 * a2 + d1 * c2,
        c1 * b2 + d1 * d2,
        e1 * a2 + f1 * c2 + e2,
        e1 * b2 + f1 * d2 + f2,
    )


def placements(page):
    """(x_mm, y_mm, w_mm, h_mm) for each painted image XObject."""
    ctm = IDENTITY
    stack = []
    out = []
    for operands, op in ContentStream(page.get_contents(), None).operations:
        if op == b"q":
            stack.append(ctm)
        elif op == b"Q":
            ctm = stack.pop() if stack else IDENTITY
        elif op == b"cm":
            ctm = mul(tuple(float(o) for o in operands), ctm)
        elif op == b"Do":
            a, b, c, d, e, f = ctm
            # A unit image square maps through the CTM; width/height are the
            # column norms, which handles flips and rotation correctly.
            w = (a * a + b * b) ** 0.5
            h = (c * c + d * d) ** 0.5
            out.append((e * MM_PER_PT, f * MM_PER_PT, w * MM_PER_PT, h * MM_PER_PT))
    return out


def main(path, sheet_px=2480, badge_px=685, expect_mm=58.0, tol_mm=0.5):
    """
    Two different PDF shapes have to be measured differently:

      * backend PDF  - one image PER BADGE, already at its final size, so the
                       placement width IS the badge diameter.
      * browser print - ONE image for the whole sheet, so a badge's size is
                       its fraction of that bitmap (badge_px / sheet_px).

    Deciding by "is this image roughly the whole page" keeps both honest.
    """
    reader = pypdf.PdfReader(path)
    print(f"file  : {path}")
    print(f"pages : {len(reader.pages)}")

    worst = 0.0
    measured = 0

    for i, page in enumerate(reader.pages):
        pw = float(page.mediabox.width) * MM_PER_PT
        ph = float(page.mediabox.height) * MM_PER_PT
        found = placements(page)
        print(f"\npage {i + 1}: {pw:.3f} x {ph:.3f} mm   ({len(found)} image(s))")

        for idx, (x, y, w, h) in enumerate(found):
            is_full_sheet = w >= pw * 0.9 and h >= ph * 0.9
            if is_full_sheet:
                badge = w * (badge_px / sheet_px)
                kind = f"full-sheet bitmap {w:.3f} x {h:.3f} mm"
            else:
                badge = w
                kind = f"badge image at ({x:.1f}, {y:.1f})"

            err = badge - expect_mm
            worst = max(worst, abs(err))
            measured += 1
            if idx < 3 or is_full_sheet:
                print(
                    f"  {kind}\n"
                    f"    -> badge measures {badge:.4f} mm  (error {err:+.4f} mm)"
                )
        if len(found) > 3 and not any(w >= pw * 0.9 for _, _, w, _ in found):
            print(f"  ... {len(found) - 3} more badges, all measured")

    verdict = "PASS" if worst <= tol_mm else "FAIL"
    print(
        f"\n{measured} badge(s) measured | worst error {worst:+.4f} mm "
        f"| tolerance +/-{tol_mm} mm -> {verdict}"
    )


if __name__ == "__main__":
    main(*sys.argv[1:2])
