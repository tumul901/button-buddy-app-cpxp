"""
Layout preview endpoint.

The frontend needs to know how many badges fit before it commits to an export.
It has its own mirrored implementation for instant feedback while dragging a
slider, but this endpoint is the authority — and the parity test
(tests/test_layout.py) keeps the two honest.
"""

from typing import Literal, Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.config import RULER_BAND_MM
from app.services.layout import PAPER_SIZES_MM, compute_layout
from app.utils.http import bad_request

router = APIRouter(prefix="/layout", tags=["layout"])


class LayoutQuery(BaseModel):
    paper: str = "A4"
    orientation: Literal["portrait", "landscape"] = "portrait"
    diameter_mm: float = Field(default=58.0, gt=0, le=500)
    bleed_mm: float = Field(default=0.0, ge=0, le=50)
    gap_mm: float = Field(default=5.0, ge=0, le=50)
    margin_mm: float = Field(default=10.0, ge=0, le=50)
    copies: Optional[int] = Field(default=None, ge=1, le=2000)
    include_ruler: bool = True


@router.get("/papers")
def list_papers():
    """Paper sizes the backend can actually produce."""
    return [
        {"id": key, "w_mm": dims["w"], "h_mm": dims["h"]}
        for key, dims in PAPER_SIZES_MM.items()
    ]


@router.post("")
def preview_layout(q: LayoutQuery):
    footprint = q.diameter_mm + 2.0 * q.bleed_mm
    try:
        return compute_layout(
            paper=q.paper,
            diameter_mm=footprint,
            gap_mm=q.gap_mm,
            margin_mm=q.margin_mm,
            orientation=q.orientation,
            copies=q.copies,
            reserve_top_mm=RULER_BAND_MM if q.include_ruler else 0.0,
        )
    except ValueError as exc:
        bad_request(str(exc))
