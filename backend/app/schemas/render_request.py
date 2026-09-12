from typing import Optional

from pydantic import BaseModel, Field

from app.config import MAX_BLEED_MM, MAX_DIAMETER_MM, MIN_DIAMETER_MM


class CropParams(BaseModel):
    """
    Crop offsets are NORMALISED: fractions of the total badge diameter, so the
    editor preview can be any on-screen size and still match the render.
    scale is a multiplier on cover-fit; below 1.0 would expose background.
    """

    offset_x: float = Field(default=0.0, ge=-4.0, le=4.0)
    offset_y: float = Field(default=0.0, ge=-4.0, le=4.0)
    scale: float = Field(default=1.0, ge=1.0, le=8.0)


class RenderRequest(BaseModel):
    session_id: str = Field(min_length=1, max_length=64)
    # Optional: a plain photo badge with no branding is a legitimate result.
    template_id: Optional[str] = Field(default=None, max_length=64)
    diameter_mm: float = Field(default=58.0, ge=MIN_DIAMETER_MM, le=MAX_DIAMETER_MM)
    bleed_mm: float = Field(default=0.0, ge=0.0, le=MAX_BLEED_MM)
    crop: CropParams = Field(default_factory=CropParams)


class RenderResponse(BaseModel):
    session_id: str
    composite_url: str
    badge_px: int
    bleed_px: int
    total_px: int
    diameter_mm: float
    bleed_mm: float
    total_diameter_mm: float
    dpi: int
    render_version: int
    crop: CropParams
