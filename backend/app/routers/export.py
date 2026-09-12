import logging
import os

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlmodel import Session

from app.database import get_session
from app.models.session import BadgeSession
from app.schemas.export_request import ExportRequest, ExportResponse
from app.services import storage
from app.services.pdf_exporter import export_pdf
from app.services.sheet_exporter import export_png_sheets
from app.utils.http import bad_request, conflict

router = APIRouter(prefix="/export", tags=["export"])
log = logging.getLogger(__name__)

# Diameters within this tolerance are treated as the same size.
DIAMETER_EPSILON_MM = 0.01


class Resolved:
    def __init__(self, paths: list[str], diameter_mm: float, bleed_mm: float, primary_id: str):
        self.paths = paths
        self.diameter_mm = diameter_mm
        self.bleed_mm = bleed_mm
        self.primary_id = primary_id


def _resolve(req: ExportRequest, db: Session) -> Resolved:
    """
    Build the placement sequence and determine the sheet's badge size.

    Mixed diameters are rejected outright. v1 assigned `diameter_mm` inside the
    loop, so it silently kept whichever session came last and printed every
    badge at that size — the one failure mode this product must never have.
    """
    if req.items:
        sessions: list[tuple[BadgeSession, int]] = []
        missing: list[str] = []
        for item in req.items:
            sess = db.get(BadgeSession, item.session_id)
            if not sess:
                missing.append(item.session_id)
                continue
            if not storage.exists(sess.composite_key):
                missing.append(item.session_id)
                continue
            sessions.append((sess, item.copies))

        if not sessions:
            bad_request(
                "None of the selected badges have been rendered yet. "
                "Render them in the editor first."
            )

        diameters = {round(s.diameter_mm, 2) for s, _ in sessions}
        bleeds = {round(s.bleed_mm, 2) for s, _ in sessions}
        if len(diameters) > 1:
            conflict(
                "These badges were rendered at different diameters ("
                + ", ".join(f"{d:g} mm" for d in sorted(diameters))
                + "). A sheet has one badge size — re-render them all at the "
                "same diameter before printing."
            )
        if len(bleeds) > 1:
            conflict(
                "These badges were rendered with different bleed values. "
                "Re-render them all with the same bleed before printing."
            )

        if missing:
            log.warning("export skipped %d unrendered session(s)", len(missing))

        paths: list[str] = []
        for sess, copies in sessions:
            paths.extend([storage.abs_path(sess.composite_key)] * copies)

        first = sessions[0][0]
        return Resolved(paths, first.diameter_mm, first.bleed_mm, first.id)

    sess = db.get(BadgeSession, req.session_id)
    if not sess:
        raise HTTPException(status_code=404, detail="Session not found")
    if not storage.exists(sess.composite_key):
        bad_request("This badge has not been rendered yet. Render it in the editor first.")
    return Resolved([storage.abs_path(sess.composite_key)], sess.diameter_mm, sess.bleed_mm, sess.id)


def _check_expected(req: ExportRequest, actual_mm: float) -> None:
    """
    Reject a print whose size differs from what the client is showing the user.
    Catches the "changed the slider after rendering" case, where the UI would
    otherwise promise one diameter and the PDF deliver another.
    """
    if req.expect_diameter_mm is None:
        return
    if abs(req.expect_diameter_mm - actual_mm) > DIAMETER_EPSILON_MM:
        conflict(
            f"These badges were rendered at {actual_mm:g} mm but you are printing at "
            f"{req.expect_diameter_mm:g} mm. Re-render them at {req.expect_diameter_mm:g} mm first "
            "so the printed size is exactly what you asked for."
        )


@router.post("/png-sheet", response_model=ExportResponse)
def export_png_sheet(req: ExportRequest, db: Session = Depends(get_session)):
    """Render the print sheet as PNG(s) at 300 DPI — one file per page."""
    resolved = _resolve(req, db)
    _check_expected(req, resolved.diameter_mm)

    out_dir = storage.ensure_parent(storage.session_key(resolved.primary_id, "x"))
    out_dir = os.path.dirname(out_dir)
    stem = f"sheet_{req.paper}_{req.orientation}"

    try:
        result = export_png_sheets(
            output_dir=out_dir,
            filename_stem=stem,
            paper=req.paper,
            orientation=req.orientation,
            diameter_mm=resolved.diameter_mm,
            bleed_mm=resolved.bleed_mm,
            gap_mm=req.gap_mm,
            margin_mm=req.margin_mm,
            badge_images=resolved.paths,
            copies=req.copies,
            include_ruler=req.include_ruler,
            draw_guides=req.draw_guides,
            perforation_mm=req.perforation_mm,
        )
    except ValueError as exc:
        bad_request(str(exc))

    urls = [
        f"{storage.public_url(storage.session_key(resolved.primary_id, os.path.basename(p)))}"
        f"?v={os.path.getmtime(p):.0f}"
        for p in result["files"]
    ]
    download_urls = [
        f"/api/export/download/{resolved.primary_id}/{os.path.basename(p)}"
        f"?diameter_mm={resolved.diameter_mm}"
        for p in result["files"]
    ]

    return ExportResponse(
        urls=urls,
        download_urls=download_urls,
        total_pages=result["total_pages"],
        badges_placed=result["badges_placed"],
        truncated=result["truncated"],
        layout=result["layout"],
        diameter_mm=resolved.diameter_mm,
        bleed_mm=resolved.bleed_mm,
    )


@router.post("/pdf", response_model=ExportResponse)
def export_pdf_sheet(req: ExportRequest, db: Session = Depends(get_session)):
    """
    Generate a print-ready PDF with badges at exact mm coordinates.

    PDF geometry is in points (1 pt = 1/72 in), so the physical size is
    independent of printer DPI and of the browser's print box.
    """
    resolved = _resolve(req, db)
    _check_expected(req, resolved.diameter_mm)

    pdf_key = storage.session_key(
        resolved.primary_id, f"sheet_{req.paper}_{req.orientation}.pdf"
    )
    pdf_path = storage.ensure_parent(pdf_key)

    try:
        result = export_pdf(
            output_path=pdf_path,
            paper=req.paper,
            orientation=req.orientation,
            diameter_mm=resolved.diameter_mm,
            bleed_mm=resolved.bleed_mm,
            gap_mm=req.gap_mm,
            margin_mm=req.margin_mm,
            badge_images=resolved.paths,
            copies=req.copies,
            include_ruler=req.include_ruler,
            draw_guides=req.draw_guides,
            perforation_mm=req.perforation_mm,
        )
    except ValueError as exc:
        bad_request(str(exc))

    return ExportResponse(
        urls=[f"{storage.public_url(pdf_key)}?v={os.path.getmtime(pdf_path):.0f}"],
        download_urls=[
            f"/api/export/download/{resolved.primary_id}/{os.path.basename(pdf_path)}"
            f"?diameter_mm={resolved.diameter_mm}"
        ],
        total_pages=result["total_pages"],
        badges_placed=result["badges_placed"],
        truncated=result["truncated"],
        layout=result["layout"],
        diameter_mm=resolved.diameter_mm,
        bleed_mm=resolved.bleed_mm,
    )


def _friendly_name(paper: str, orientation: str, diameter_mm: float | None, ext: str, page: int | None = None) -> str:
    size = f"{diameter_mm:.0f}mm-" if diameter_mm else ""
    suffix = f"-page{page}" if page else ""
    return f"button-buddy-{size}{paper}-{orientation}{suffix}{ext}"


@router.get("/download/{session_id}/{filename}")
def download_artifact(
    session_id: str,
    filename: str,
    diameter_mm: float | None = None,
):
    """
    Serve a generated sheet as a download.

    The filename is set server-side via Content-Disposition rather than by the
    client's `download` attribute. Browsers ignore that attribute in several
    situations - when `target="_blank"` is also present, for cross-origin URLs,
    and under some managed-browser policies - and then fall back to naming the
    file after the URL or the blob UUID, producing an extensionless file the OS
    cannot open. A server-set Content-Disposition cannot be overridden.
    """
    # storage.abs_path refuses traversal, so a crafted filename cannot escape.
    if "/" in filename or "\\" in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")

    key = storage.session_key(session_id, filename)
    if not storage.exists(key):
        raise HTTPException(status_code=404, detail="That file has not been generated yet")

    ext = os.path.splitext(filename)[1].lower()
    media = {".pdf": "application/pdf", ".png": "image/png"}.get(ext)
    if media is None:
        raise HTTPException(status_code=400, detail="Unsupported file type")

    # sheet_A4_portrait_p2.png -> paper A4, orientation portrait, page 2
    stem = os.path.splitext(filename)[0]
    parts = stem.split("_")
    paper = parts[1] if len(parts) > 1 else "sheet"
    orientation = parts[2] if len(parts) > 2 else ""
    page = None
    if len(parts) > 3 and parts[3].startswith("p") and parts[3][1:].isdigit():
        page = int(parts[3][1:])

    return FileResponse(
        storage.abs_path(key),
        media_type=media,
        filename=_friendly_name(paper, orientation, diameter_mm, ext, page),
    )


@router.get("/pdf/{session_id}")
def download_pdf(
    session_id: str,
    paper: str = "A4",
    orientation: str = "portrait",
    diameter_mm: float | None = None,
):
    """Download the generated PDF with a friendly filename."""
    key = storage.session_key(session_id, f"sheet_{paper}_{orientation}.pdf")
    if not storage.exists(key):
        raise HTTPException(status_code=404, detail="PDF not generated yet")
    return FileResponse(
        storage.abs_path(key),
        media_type="application/pdf",
        filename=_friendly_name(paper, orientation, diameter_mm, ".pdf"),
    )
