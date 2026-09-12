import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlmodel import Field, SQLModel


def _now() -> datetime:
    """Timezone-aware UTC. datetime.utcnow() is deprecated from Python 3.12."""
    return datetime.now(timezone.utc)


class BadgeSession(SQLModel, table=True):
    __tablename__ = "badge_sessions"

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    # Storage-relative keys ("sessions/<id>/photo.png"), never absolute paths.
    photo_key: str = Field(max_length=500)
    composite_key: Optional[str] = Field(default=None, max_length=500)
    template_id: Optional[str] = Field(default=None, foreign_key="templates.id")
    diameter_mm: float = Field(default=58.0)
    bleed_mm: float = Field(default=0.0)
    crop_offset_x: float = Field(default=0.0)
    crop_offset_y: float = Field(default=0.0)
    crop_scale: float = Field(default=1.0)
    photo_w: int = Field(default=0)
    photo_h: int = Field(default=0)
    # Bumped on every render so clients can cache-bust deterministically.
    render_version: int = Field(default=0)
    print_config: Optional[str] = Field(default=None)
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)
