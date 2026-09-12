import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlmodel import Field, SQLModel


def _now() -> datetime:
    return datetime.now(timezone.utc)


class BadgeTemplate(SQLModel, table=True):
    __tablename__ = "templates"

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    name: str = Field(max_length=100)
    category: str = Field(max_length=50, default="general")
    file_key: str = Field(max_length=500)
    thumbnail_key: str = Field(max_length=500)
    width: int = Field(default=0)
    height: int = Field(default=0)
    is_builtin: bool = Field(default=False)
    created_at: datetime = Field(default_factory=_now)
