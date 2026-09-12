import logging
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, UploadFile
from PIL import Image
from pydantic import BaseModel
from sqlmodel import Session, select

from app.config import ADMIN_TOKEN
from app.database import get_session
from app.models.template import BadgeTemplate
from app.services import storage
from app.services.uploads import save_upload_image

router = APIRouter(prefix="/templates", tags=["templates"])
log = logging.getLogger(__name__)

THUMB_PX = 256


class TemplateResponse(BaseModel):
    id: str
    name: str
    category: str
    thumbnail_url: str
    full_url: str
    width: int
    height: int
    is_square: bool


def require_admin(x_admin_token: Optional[str] = Header(default=None)) -> None:
    """
    Gate the write endpoints. Templates are shown to every user, so an
    unauthenticated upload endpoint lets anyone change what everyone sees.
    Disabled (open) when ADMIN_TOKEN is unset, for local development.
    """
    if ADMIN_TOKEN is None:
        return
    if x_admin_token != ADMIN_TOKEN:
        raise HTTPException(status_code=401, detail="Admin token required")


def format_tpl(tpl: BadgeTemplate) -> TemplateResponse:
    return TemplateResponse(
        id=tpl.id,
        name=tpl.name,
        category=tpl.category,
        thumbnail_url=storage.public_url(tpl.thumbnail_key),
        full_url=storage.public_url(tpl.file_key),
        width=tpl.width,
        height=tpl.height,
        is_square=tpl.width == tpl.height,
    )


@router.get("", response_model=list[TemplateResponse])
def list_templates(db: Session = Depends(get_session)):
    """All branding templates. Rows whose files are missing are skipped rather
    than failing the whole listing."""
    rows = db.exec(select(BadgeTemplate).order_by(BadgeTemplate.created_at)).all()
    out = []
    for t in rows:
        if not t.file_key or not t.thumbnail_key:
            log.warning("template %s has no files; skipping", t.id)
            continue
        out.append(format_tpl(t))
    return out


@router.get("/{template_id}", response_model=TemplateResponse)
def get_template(template_id: str, db: Session = Depends(get_session)):
    tpl = db.get(BadgeTemplate, template_id)
    if not tpl or not tpl.file_key:
        raise HTTPException(status_code=404, detail="Template not found")
    return format_tpl(tpl)


@router.post("", response_model=TemplateResponse, status_code=201)
async def upload_template(
    file: UploadFile = File(...),
    name: str = Form(...),
    category: str = Form(default="general"),
    db: Session = Depends(get_session),
    _: None = Depends(require_admin),
):
    """
    Upload a branding template (PNG with transparency works best).

    Files are written and validated before the row is committed. v1 committed
    an empty-path row first, so one failed upload left a record whose empty
    path made the whole template listing raise for every user.
    """
    name = name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Template name is required")

    tpl = BadgeTemplate(name=name[:100], category=(category or "general")[:50], file_key="", thumbnail_key="")

    saved = await save_upload_image(file, storage.template_key(tpl.id, "full"), max_side=2000)

    thumb_key = storage.template_key(tpl.id, "thumb.png")
    thumb_path = storage.ensure_parent(thumb_key)
    try:
        with Image.open(storage.abs_path(saved.key)) as img:
            thumb = img.convert("RGBA")
            thumb.thumbnail((THUMB_PX, THUMB_PX), Image.LANCZOS)
            thumb.save(thumb_path, "PNG", optimize=True)
    except Exception:
        storage.remove_template_dir(tpl.id)
        raise

    tpl.file_key = saved.key
    tpl.thumbnail_key = thumb_key
    tpl.width = saved.width
    tpl.height = saved.height

    try:
        db.add(tpl)
        db.commit()
        db.refresh(tpl)
    except Exception:
        storage.remove_template_dir(tpl.id)
        raise

    log.info("template %s (%s) uploaded", tpl.id, tpl.name)
    return format_tpl(tpl)


@router.delete("/{template_id}", status_code=204)
def delete_template(
    template_id: str,
    db: Session = Depends(get_session),
    _: None = Depends(require_admin),
):
    tpl = db.get(BadgeTemplate, template_id)
    if not tpl:
        raise HTTPException(status_code=404, detail="Template not found")
    db.delete(tpl)
    db.commit()
    storage.remove_template_dir(template_id)
    log.info("template %s deleted", template_id)
