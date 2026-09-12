from typing import Literal, Optional

from pydantic import BaseModel, Field, model_validator

PaperLiteral = Literal["A4", "A3", "Letter", "Legal", "4x6", "4x6in"]


class BadgeExportItem(BaseModel):
    session_id: str = Field(min_length=1, max_length=64)
    copies: int = Field(default=1, ge=1, le=500)


class ExportRequest(BaseModel):
    # Single-badge export.
    session_id: Optional[str] = Field(default=None, max_length=64)
    # Multi-badge batch; takes precedence when present.
    items: Optional[list[BadgeExportItem]] = Field(default=None, max_length=500)

    paper: PaperLiteral = "A4"
    orientation: Literal["portrait", "landscape"] = "portrait"
    # None means "fill the page".
    copies: Optional[int] = Field(default=None, ge=1, le=2000)
    gap_mm: float = Field(default=5.0, ge=0.0, le=50.0)
    margin_mm: float = Field(default=10.0, ge=0.0, le=50.0)
    include_ruler: bool = True
    draw_guides: bool = True
    # Extra DIAMETER beyond the badge for the cutter/perforation ring.
    # 0 disables it. See config.DEFAULT_PERFORATION_MM.
    perforation_mm: float = Field(default=12.0, ge=0.0, le=40.0)
    # When set, the client asserts the diameter it believes it is printing.
    # A mismatch against the stored render is rejected rather than silently
    # printing the wrong physical size.
    expect_diameter_mm: Optional[float] = Field(default=None, gt=0, le=500)

    @model_validator(mode="after")
    def _one_source(self):
        if not self.session_id and not self.items:
            raise ValueError("Provide either session_id or items")
        return self


class ExportResponse(BaseModel):
    urls: list[str]
    # Attachment endpoints. Filenames are set server-side via
    # Content-Disposition, which no client-side attribute or browser policy
    # can override.
    download_urls: list[str] = []
    total_pages: int
    badges_placed: int
    truncated: bool
    layout: dict
    diameter_mm: float
    bleed_mm: float
