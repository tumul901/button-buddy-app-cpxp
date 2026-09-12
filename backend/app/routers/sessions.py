import logging
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from sqlmodel import Session

from app.config import MAX_BLEED_MM, MAX_DIAMETER_MM, MIN_DIAMETER_MM
from app.database import get_session
from app.models.session import BadgeSession, _now
from app.services import storage
from app.services.uploads import save_upload_image
from app.utils.http import bad_request

router = APIRouter(prefix="/sessions", tags=["sessions"])
log = logging.getLogger(__name__)


class SessionResponse(BaseModel):
    """
    Explicit response model: the ORM row carries filesystem keys and internal
    columns that must not leak to clients.
    """

    id: str
    photo_url: str
    composite_url: Optional[str] = None
    template_id: Optional[str] = None
    diameter_mm: float
    bleed_mm: float
    crop: dict
    photo_w: int
    photo_h: int
    render_version: int


def to_response(sess: BadgeSession) -> SessionResponse:
    return SessionResponse(
        id=sess.id,
        photo_url=storage.public_url(sess.photo_key),
        composite_url=(
            f"{storage.public_url(sess.composite_key)}?v={sess.render_version}"
            if sess.composite_key
            else None
        ),
        template_id=sess.template_id,
        diameter_mm=sess.diameter_mm,
        bleed_mm=sess.bleed_mm,
        crop={
            "offset_x": sess.crop_offset_x,
            "offset_y": sess.crop_offset_y,
            "scale": sess.crop_scale,
        },
        photo_w=sess.photo_w,
        photo_h=sess.photo_h,
        render_version=sess.render_version,
    )


@router.post("", response_model=SessionResponse, status_code=201)
async def create_session(
    photo: UploadFile = File(...),
    diameter_mm: float = Form(default=58.0),
    bleed_mm: float = Form(default=0.0),
    template_id: str = Form(default=""),
    db: Session = Depends(get_session),
):
    """
    Create a badge session from an uploaded photo.

    The file is size-capped while streaming and verified to be a real image
    before anything is persisted; the stored extension comes from the format
    Pillow detected, never from the client's filename.
    """
    if not (MIN_DIAMETER_MM <= diameter_mm <= MAX_DIAMETER_MM):
        bad_request(
            f"Diameter must be between {MIN_DIAMETER_MM:.0f} and {MAX_DIAMETER_MM:.0f} mm"
        )
    if not (0.0 <= bleed_mm <= MAX_BLEED_MM):
        bad_request(f"Bleed must be between 0 and {MAX_BLEED_MM:.0f} mm")

    sess = BadgeSession(
        photo_key="",
        diameter_mm=diameter_mm,
        bleed_mm=bleed_mm,
        template_id=template_id or None,
    )

    # Write the file first; only commit a row once there is a real photo behind
    # it, so a failed upload cannot leave a dangling record.
    saved = await save_upload_image(photo, storage.session_key(sess.id, "photo"))

    sess.photo_key = saved.key
    sess.photo_w = saved.width
    sess.photo_h = saved.height
    try:
        db.add(sess)
        db.commit()
        db.refresh(sess)
    except Exception:
        storage.remove_session_dir(sess.id)
        raise

    log.info("session %s created (%dx%d)", sess.id, saved.width, saved.height)
    return to_response(sess)


@router.get("/{session_id}", response_model=SessionResponse)
def get_session_data(session_id: str, db: Session = Depends(get_session)):
    """Rehydrate a session — lets the frontend survive a page refresh."""
    sess = db.get(BadgeSession, session_id)
    if not sess:
        raise HTTPException(status_code=404, detail="Session not found")
    return to_response(sess)


@router.delete("/{session_id}", status_code=204)
def delete_session(session_id: str, db: Session = Depends(get_session)):
    sess = db.get(BadgeSession, session_id)
    if not sess:
        raise HTTPException(status_code=404, detail="Session not found")
    db.delete(sess)
    db.commit()
    storage.remove_session_dir(session_id)
    log.info("session %s deleted", session_id)


@router.patch("/{session_id}", response_model=SessionResponse)
def touch_session(session_id: str, db: Session = Depends(get_session)):
    """Keep a session alive against the TTL sweep while the user is working."""
    sess = db.get(BadgeSession, session_id)
    if not sess:
        raise HTTPException(status_code=404, detail="Session not found")
    sess.updated_at = _now()
    db.add(sess)
    db.commit()
    db.refresh(sess)
    return to_response(sess)
