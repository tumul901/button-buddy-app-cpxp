import os
import glob
from PIL import Image
from reportlab.lib.units import mm
from app.services.compositor import composite_badge
from app.services.pdf_exporter import export_pdf
from app.services.units import mm_to_px

print("=== 1. Test Units ===")
px_58 = mm_to_px(58.0)
print(f"58 mm -> {px_58} px at 300 DPI")
assert px_58 == 685, f"Expected 685 px, got {px_58}"

# Verify points to mm conversion
pt_58 = 58.0 * mm
mm_reconstructed = pt_58 / 72.0 * 25.4
print(f"58 mm in PDF points: {pt_58:.4f} pt -> reconstructed: {mm_reconstructed:.4f} mm")
assert abs(mm_reconstructed - 58.0) < 1e-6, "Mathematical inaccuracy in point conversion"

print("=== 2. Test Compositor with 58mm ===")
tpl_path = "./uploads/templates/tpl_1.png"
photos = glob.glob("./uploads/sessions/*/photo.*")
if not photos:
    dummy = Image.new("RGBA", (800, 800), (100, 150, 200, 255))
    os.makedirs("./uploads/test", exist_ok=True)
    dummy.save("./uploads/test/photo.png")
    photo_path = "./uploads/test/photo.png"
else:
    photo_path = photos[0]

os.makedirs("./uploads/test", exist_ok=True)
out_png = "./uploads/test/test_badge_58mm.png"
res = composite_badge(
    photo_path=photo_path,
    template_path=tpl_path,
    diameter_mm=58.0,
    bleed_mm=0.0,
    crop_offset_x=0.0,
    crop_offset_y=0.0,
    crop_scale=1.0,
    output_path=out_png,
)
print("Compositor result:", res)
img = Image.open(out_png)
print(f"Saved image dimensions: {img.width}x{img.height}, DPI: {img.info.get('dpi')}")
assert img.width == 685 and img.height == 685, f"Image size {img.size} is not 685x685"
assert round(img.info.get("dpi")[0]) == 300, "Image DPI is not 300"

print("=== 3. Test PDF Exporter with 58mm ===")
out_pdf = "./uploads/test/test_badge_58mm.pdf"
pdf_res = export_pdf(
    output_path=out_pdf,
    paper="A4",
    orientation="portrait",
    diameter_mm=58.0,
    bleed_mm=0.0,
    gap_mm=5.0,
    margin_mm=10.0,
    badge_images=[out_png] * 12,
)
print("PDF exporter result:", pdf_res)
assert os.path.exists(out_pdf), "PDF file was not created"
print(f"PDF file size: {os.path.getsize(out_pdf)} bytes")

print("=== 4. Test Dynamic Diameter (40mm and 75mm) ===")
for d in [40.0, 75.0]:
    d_px = mm_to_px(d)
    out_d_png = f"./uploads/test/test_badge_{int(d)}mm.png"
    composite_badge(
        photo_path=photo_path,
        template_path=tpl_path,
        diameter_mm=d,
        bleed_mm=0.0,
        crop_offset_x=0.0,
        crop_offset_y=0.0,
        crop_scale=1.0,
        output_path=out_d_png,
    )
    img_d = Image.open(out_d_png)
    assert img_d.width == d_px and img_d.height == d_px, f"{d}mm failed: got {img_d.size}, expected {d_px}x{d_px}"
    print(f"[OK] Dynamic diameter {d}mm -> {d_px}px exact match")

print("=== ALL PHYSICAL PRINT ACCURACY TESTS PASSED PERFECTLY ===")
