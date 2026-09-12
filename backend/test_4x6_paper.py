import os
from reportlab.lib.units import mm
from app.services.layout import compute_layout
from app.services.pdf_exporter import export_pdf

print("=== Test 4x6 Layout (Portrait) ===")
l_port = compute_layout(
    paper="4x6",
    diameter_mm=58.0,
    gap_mm=5.0,
    margin_mm=5.0,
    orientation="portrait",
)
print("4x6 Portrait Layout:", l_port)
assert l_port["paper_mm"]["w"] == 101.6 and l_port["paper_mm"]["h"] == 152.4
print(f"Badges fitting on 4x6 portrait: {l_port['cols']} cols x {l_port['rows']} rows = {l_port['total_badges']} badges")

print("=== Test 4x6 Layout (Landscape) ===")
l_land = compute_layout(
    paper="4x6",
    diameter_mm=58.0,
    gap_mm=5.0,
    margin_mm=5.0,
    orientation="landscape",
)
print("4x6 Landscape Layout:", l_land)
assert l_land["paper_mm"]["w"] == 152.4 and l_land["paper_mm"]["h"] == 101.6
print(f"Badges fitting on 4x6 landscape: {l_land['cols']} cols x {l_land['rows']} rows = {l_land['total_badges']} badges")

print("=== Test 4x6 PDF Generation ===")
sample_badge = "./uploads/test/test_badge_58mm.png"
out_4x6_pdf = "./uploads/test/test_badge_4x6.pdf"
pdf_res = export_pdf(
    output_path=out_4x6_pdf,
    paper="4x6",
    orientation="portrait",
    diameter_mm=58.0,
    bleed_mm=0.0,
    gap_mm=5.0,
    margin_mm=5.0,
    badge_images=[sample_badge] * 2,
)
print("4x6 PDF Result:", pdf_res)
assert os.path.exists(out_4x6_pdf)
print(f"4x6 PDF generated successfully: {os.path.getsize(out_4x6_pdf)} bytes")

import pypdfium2 as pdfium
doc = pdfium.PdfDocument(out_4x6_pdf)
page = doc[0]
w_pt, h_pt = page.get_size()
print(f"4x6 PDF Page points: {w_pt:.2f} x {h_pt:.2f} pt")
w_mm = w_pt / 72.0 * 25.4
h_mm = h_pt / 72.0 * 25.4
print(f"4x6 PDF Page physical dimensions: {w_mm:.2f} x {h_mm:.2f} mm")
print("Expected: 101.60 x 152.40 mm (4.00 x 6.00 in)")
assert abs(w_mm - 101.6) < 0.1, f"Width mismatch: {w_mm}"
assert abs(h_mm - 152.4) < 0.1, f"Height mismatch: {h_mm}"
print("[OK] 4x6 INCH PAPER OPTION VERIFIED PHYSICALLY ACCURATE!")
