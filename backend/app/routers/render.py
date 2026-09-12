import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session

from app.database import get_session
from app.models.session import BadgeSession, _now
from app.models.template import BadgeTemplate
from app.schemas.render_request import CropParams, RenderRequest, RenderResponse
from app.services import storage
from app.services.compositor import CompositeError, composite_badge
from app.utils.http import bad_request

router = APIRouter(prefix="/render", tags=["render"])
log = logging.getLogger(__name__)


@router.post("", response_model=RenderResponse)
def render_badge(req: RenderRequest, db: Session = Depends(get_session)):
    """
    Composite the user photo + branding template into a print-resolution badge.

        badge_px = round(diameter_mm * 300 / 25.4)

    where 25.4 is the exact number of mm per inch. Crop offsets arrive
    normalised (fractions of the badge diameter), so the result matches the
    editor preview regardless of how large that preview is on screen.
    """
    sess = db.get(BadgeSession, req.session_id)
    if not sess:
        raise HTTPException(status_code=404, detail="Session not found")

    if not storage.exists(sess.photo_key):
        bad_request("The photo for this session is missing. Please upload it again.")

    template_path = None
    if req.template_id:
        tpl = db.get(BadgeTemplate, req.template_id)
        if not tpl:
            raise HTTPException(status_code=404, detail="Template not found")
        if storage.exists(tpl.file_key):
            template_path = storage.abs_path(tpl.file_key)
        else:
            # Never fail the render over missing branding — the photo badge is
            # still a valid result — but say so loudly in the log.
            log.error("template %s file missing: %s", tpl.id, tpl.file_key)

    composite_key = storage.session_key(sess.id, "composite.png")
    output_path = storage.ensure_parent(composite_key)

    try:
        result = composite_badge(
            photo_path=storage.abs_path(sess.photo_key),
            template_path=template_path,
            diameter_mm=req.diameter_mm,
            bleed_mm=req.bleed_mm,
            crop_offset_x=req.crop.offset_x,
            crop_offset_y=req.crop.offset_y,
            crop_scale=req.crop.scale,
            output_path=output_path,
        )
    except CompositeError as exc:
        bad_request(str(exc))

    clamped = result["crop"]
    sess.composite_key = composite_key
    sess.template_id = req.template_id
    sess.diameter_mm = req.diameter_mm
    sess.bleed_mm = req.bleed_mm
    sess.crop_offset_x = clamped["offset_x"]
    sess.crop_offset_y = clamped["offset_y"]
    sess.crop_scale = clamped["scale"]
    sess.render_version += 1
    sess.updated_at = _now()
    db.add(sess)
    db.commit()
    db.refresh(sess)

    return RenderResponse(
        session_id=sess.id,
        # Versioned URL: the file path is stable, so without this the browser
        # keeps showing the previous render.
        composite_url=f"{storage.public_url(composite_key)}?v={sess.render_version}",
        badge_px=result["badge_px"],
        bleed_px=result["bleed_px"],
        total_px=result["total_px"],
        diameter_mm=result["diameter_mm"],
        bleed_mm=result["bleed_mm"],
        total_diameter_mm=result["total_diameter_mm"],
        dpi=result["dpi"],
        render_version=sess.render_version,
        crop=CropParams(**clamped),
    )
