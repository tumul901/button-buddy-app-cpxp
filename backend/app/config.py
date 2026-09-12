"""
Application configuration.

All values are environment-overridable so the same image can run in dev,
docker-compose and production without code changes.
"""

import os
from dotenv import load_dotenv

load_dotenv()


def _bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, "") or default)
    except ValueError:
        return default


DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./buttonbuddy.db")

# Always absolute: DB rows store storage-relative keys, resolved against this.
UPLOAD_DIR: str = os.path.abspath(os.getenv("UPLOAD_DIR", "./uploads"))

# Print resolution. 300 DPI is the industry minimum for photo-quality badges.
PRINT_DPI: int = _int("PRINT_DPI", 300)

# Upload limits (bytes). Enforced while streaming, not just advertised.
MAX_UPLOAD_BYTES: int = _int("MAX_UPLOAD_BYTES", 20 * 1024 * 1024)

# Reject absurd pixel counts before Pillow tries to decode them (decompression bombs).
MAX_IMAGE_PIXELS: int = _int("MAX_IMAGE_PIXELS", 80_000_000)

# Badge geometry guard rails (mm).
MIN_DIAMETER_MM: float = 20.0
MAX_DIAMETER_MM: float = 150.0
MAX_BLEED_MM: float = 20.0

# Vertical band reserved at the top of a sheet for the calibration ruler.
RULER_BAND_MM: float = 12.0

# Perforation / cutter ring: how much LARGER than the badge the cut circle is,
# in total diameter. Badge presses need a paper disc wider than the trim so the
# rim can be folded around the shell; 12 mm suits most 58 mm machines, but the
# allowance differs per press, so it is user-adjustable.
DEFAULT_PERFORATION_MM: float = 12.0
MAX_PERFORATION_MM: float = 40.0

# Safety cap on how many sheet pages a single export may produce.
MAX_EXPORT_PAGES: int = _int("MAX_EXPORT_PAGES", 20)

CORS_ORIGINS: list[str] = [
    o.strip()
    for o in os.getenv(
        "CORS_ORIGINS", "http://localhost:5173,http://localhost:3000"
    ).split(",")
    if o.strip()
]

# When set, POST/DELETE /api/templates require `X-Admin-Token: <value>`.
ADMIN_TOKEN: str | None = os.getenv("ADMIN_TOKEN") or None

# Delete sessions (rows + files) older than this. 0 disables the sweep.
SESSION_TTL_HOURS: int = _int("SESSION_TTL_HOURS", 72)

LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO").upper()
DEBUG: bool = _bool("DEBUG", False)
