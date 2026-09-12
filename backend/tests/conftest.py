import os
import sys

# The app is imported as `app.*`, so the backend root must be importable
# whether pytest runs from repo root or from backend/.
BACKEND_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_ROOT not in sys.path:
    sys.path.insert(0, BACKEND_ROOT)

import pytest
from PIL import Image

REPO_ROOT = os.path.dirname(BACKEND_ROOT)
TEST_PHOTO = os.path.join(REPO_ROOT, "test", "photo_1788510287426_h9jw6w.jpg")


@pytest.fixture(scope="session")
def photo_path(tmp_path_factory) -> str:
    """The real supplied test photo when present, else a synthetic stand-in."""
    if os.path.exists(TEST_PHOTO):
        return TEST_PHOTO
    p = tmp_path_factory.mktemp("photo") / "photo.png"
    img = Image.new("RGB", (1200, 1200), (80, 120, 200))
    img.save(p)
    return str(p)


@pytest.fixture(scope="session")
def portrait_photo_path(tmp_path_factory) -> str:
    """A deliberately non-square photo, to exercise cover-fit and clamping."""
    p = tmp_path_factory.mktemp("photo") / "portrait.png"
    Image.new("RGB", (600, 1500), (200, 90, 60)).save(p)
    return str(p)


@pytest.fixture(scope="session")
def template_path(tmp_path_factory) -> str:
    """A ring template: opaque near the rim, transparent in the middle."""
    from PIL import ImageDraw

    size = 1000
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse([10, 10, size - 10, size - 10], outline=(212, 175, 55, 255), width=40)
    p = tmp_path_factory.mktemp("tpl") / "ring.png"
    img.save(p)
    return str(p)
