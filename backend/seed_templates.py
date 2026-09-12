"""
Seed script to generate initial branding templates and populate the database.
Each template is a 1000x1000 RGBA PNG with a transparent circular center
where the user photo shows through, surrounded by decorative border/branding.
"""

import math
import os

from PIL import Image, ImageDraw, ImageFont
from sqlmodel import Session, select

from app.database import create_db_and_tables, engine
from app.models.template import BadgeTemplate
from app.services import storage

SIZE = 1000
CENTER = SIZE // 2
RADIUS = 400  # inner circle radius where photo is visible


def create_gold_champion_template() -> Image.Image:
    img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Outer decorative gold rings
    for r, col, width in [
        (485, (212, 175, 55, 255), 4),
        (475, (255, 223, 115, 240), 10),
        (460, (180, 130, 20, 255), 4),
        (415, (212, 175, 55, 230), 6),
    ]:
        draw.ellipse([CENTER - r, CENTER - r, CENTER + r, CENTER + r], outline=col, width=width)

    # Stars around the outer ring
    star_r = 445
    for deg in range(0, 360, 30):
        rad = math.radians(deg)
        x = CENTER + star_r * math.cos(rad)
        y = CENTER + star_r * math.sin(rad)
        # Small 5-point star or diamond dot
        d = 6
        draw.polygon(
            [(x, y - d), (x + d, y), (x, y + d), (x - d, y)],
            fill=(255, 230, 140, 255),
        )

    # Bottom badge ribbon / banner
    banner_w, banner_h = 320, 60
    bx0 = CENTER - banner_w // 2
    by0 = CENTER + 360
    draw.rectangle([bx0, by0, bx0 + banner_w, by0 + banner_h], fill=(180, 130, 20, 240), outline=(255, 230, 140, 255), width=3)
    
    # Text in banner
    font = _font(30)
    draw.text((CENTER, by0 + banner_h // 2), "CHAMPION", fill=(255, 255, 255, 255), anchor="mm", font=font)

    return img


def create_cyber_neon_template() -> Image.Image:
    img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Outer neon glow rings
    draw.ellipse([CENTER - 480, CENTER - 480, CENTER + 480, CENTER + 480], outline=(0, 242, 254, 180), width=4)
    draw.ellipse([CENTER - 470, CENTER - 470, CENTER + 470, CENTER + 470], outline=(254, 9, 121, 230), width=8)
    draw.ellipse([CENTER - 450, CENTER - 450, CENTER + 450, CENTER + 450], outline=(0, 242, 254, 255), width=4)
    draw.ellipse([CENTER - 410, CENTER - 410, CENTER + 410, CENTER + 410], outline=(254, 9, 121, 160), width=3)

    # Tech tick marks around perimeter
    for deg in range(0, 360, 10):
        rad = math.radians(deg)
        r1 = 450
        r2 = 465 if deg % 30 == 0 else 458
        x1 = CENTER + r1 * math.cos(rad)
        y1 = CENTER + r1 * math.sin(rad)
        x2 = CENTER + r2 * math.cos(rad)
        y2 = CENTER + r2 * math.sin(rad)
        draw.line([(x1, y1), (x2, y2)], fill=(0, 242, 254, 220), width=2 if deg % 30 == 0 else 1)

    # Bottom tag
    bx0, by0 = CENTER - 140, CENTER + 375
    draw.rounded_rectangle([bx0, by0, bx0 + 280, by0 + 44], radius=8, fill=(15, 23, 42, 240), outline=(0, 242, 254, 255), width=2)
    font = _font(22)
    draw.text((CENTER, by0 + 22), "CYBER BUDDY", fill=(0, 242, 254, 255), anchor="mm", font=font)

    return img


def create_botanical_template() -> Image.Image:
    img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Emerald rings
    draw.ellipse([CENTER - 480, CENTER - 480, CENTER + 480, CENTER + 480], outline=(16, 185, 129, 200), width=4)
    draw.ellipse([CENTER - 465, CENTER - 465, CENTER + 465, CENTER + 465], outline=(5, 150, 105, 240), width=8)
    draw.ellipse([CENTER - 420, CENTER - 420, CENTER + 420, CENTER + 420], outline=(52, 211, 153, 180), width=3)

    # Leaf sprig accents around ring
    for deg in range(0, 360, 20):
        rad = math.radians(deg)
        r = 445
        cx = CENTER + r * math.cos(rad)
        cy = CENTER + r * math.sin(rad)
        # Small elliptical leaf rotated radially
        draw.ellipse([cx - 8, cy - 5, cx + 8, cy + 5], fill=(52, 211, 153, 230), outline=(5, 150, 105, 255), width=1)

    # Bottom banner
    bx0, by0 = CENTER - 150, CENTER + 370
    draw.rounded_rectangle([bx0, by0, bx0 + 300, by0 + 48], radius=10, fill=(6, 78, 59, 240), outline=(52, 211, 153, 255), width=2)
    font = _font(22)
    draw.text((CENTER, by0 + 24), "SPECIAL EDITION", fill=(255, 255, 255, 255), anchor="mm", font=font)

    return img


def create_minimal_template() -> Image.Image:
    img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Sleek dark/white geometric dual ring
    draw.ellipse([CENTER - 480, CENTER - 480, CENTER + 480, CENTER + 480], outline=(255, 255, 255, 220), width=3)
    draw.ellipse([CENTER - 460, CENTER - 460, CENTER + 460, CENTER + 460], outline=(160, 160, 160, 140), width=2)
    draw.ellipse([CENTER - 420, CENTER - 420, CENTER + 420, CENTER + 420], outline=(255, 255, 255, 180), width=2)

    # Subtle crosshairs at 0, 90, 180, 270 degrees
    for deg in [0, 90, 180, 270]:
        rad = math.radians(deg)
        x1 = CENTER + 410 * math.cos(rad)
        y1 = CENTER + 410 * math.sin(rad)
        x2 = CENTER + 490 * math.cos(rad)
        y2 = CENTER + 490 * math.sin(rad)
        draw.line([(x1, y1), (x2, y2)], fill=(255, 255, 255, 240), width=3)

    return img


def _font(size: int) -> ImageFont.ImageFont:
    """Prefer a real face; fall back to Pillow's scalable default in containers."""
    for candidate in ("arial.ttf", "DejaVuSans.ttf", "LiberationSans-Regular.ttf"):
        try:
            return ImageFont.truetype(candidate, size)
        except OSError:
            continue
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def seed() -> int:
    """
    Create the built-in templates. Idempotent: re-running only adds what is
    missing, so it is safe to call on every boot.
    """
    create_db_and_tables()

    templates_data = [
        ("Gold Champion", "award", create_gold_champion_template),
        ("Cyber Neon Glow", "creative", create_cyber_neon_template),
        ("Botanical Emerald", "events", create_botanical_template),
        ("Minimalist Modern", "minimal", create_minimal_template),
    ]

    created = 0
    with Session(engine) as session:
        for name, category, factory in templates_data:
            existing = session.exec(
                select(BadgeTemplate).where(BadgeTemplate.name == name)
            ).first()
            if existing and storage.exists(existing.file_key):
                continue
            if existing:
                session.delete(existing)
                session.commit()
                storage.remove_template_dir(existing.id)

            tpl = BadgeTemplate(
                name=name, category=category, file_key="", thumbnail_key="", is_builtin=True
            )
            img = factory()

            # Files first, row second: a half-written template must never leave
            # a row whose missing file breaks the listing for everyone.
            file_key = storage.template_key(tpl.id, "full.png")
            thumb_key = storage.template_key(tpl.id, "thumb.png")
            img.save(storage.ensure_parent(file_key), "PNG", optimize=True)
            thumb = img.copy()
            thumb.thumbnail((256, 256), Image.LANCZOS)
            thumb.save(storage.ensure_parent(thumb_key), "PNG", optimize=True)

            tpl.file_key = file_key
            tpl.thumbnail_key = thumb_key
            tpl.width, tpl.height = img.size
            session.add(tpl)
            session.commit()
            created += 1
            print(f"Created template '{name}' ({tpl.id})")

    if created == 0:
        print("All built-in templates already present.")
    return created


if __name__ == "__main__":
    seed()
