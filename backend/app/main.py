import logging
import os
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.config import (
    CORS_ORIGINS,
    DEBUG,
    LOG_LEVEL,
    PRINT_DPI,
    SESSION_TTL_HOURS,
    UPLOAD_DIR,
)
from app.database import create_db_and_tables, healthcheck
from app.routers import export, layout, render, sessions, templates
from app.services.maintenance import sweep_expired_sessions
from app.services.migrations import ensure_compatible_schema

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
)
log = logging.getLogger("buttonbuddy")

# Directories must exist BEFORE the StaticFiles mount is constructed: it probes
# the path at __init__ and raises. Creating them in lifespan (as v1 did) is too
# late, so a fresh checkout could never start.
for sub in ("", "templates", "sessions"):
    os.makedirs(os.path.join(UPLOAD_DIR, sub), exist_ok=True)


def _ensure_templates() -> None:
    """
    Seed the built-in templates when none exist.

    An empty templates table used to dead-end the editor: rendering required a
    template, so a fresh database left the user on a screen they could not
    leave. Seeding on boot means the app is always usable out of the box.
    """
    try:
        from sqlmodel import Session, select

        from app.database import engine
        from app.models.template import BadgeTemplate

        with Session(engine) as db:
            if db.exec(select(BadgeTemplate)).first():
                return
        log.info("no templates found; seeding built-ins")
        from seed_templates import seed

        seed()
    except Exception as exc:
        # A seeding failure must not stop the API from serving.
        log.warning("template seeding skipped: %s", exc)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Must run before create_all: an older database keeps its old columns, and
    # create_all will not alter them, so every query would fail at runtime.
    ensure_compatible_schema()
    create_db_and_tables()
    log.info("upload dir: %s", UPLOAD_DIR)
    log.info("print dpi: %d", PRINT_DPI)
    _ensure_templates()
    if SESSION_TTL_HOURS > 0:
        removed = sweep_expired_sessions(SESSION_TTL_HOURS)
        if removed:
            log.info("swept %d expired session(s)", removed)
    yield


app = FastAPI(
    title="Button Buddy API",
    version="1.1.0",
    description=(
        "Backend for Button Buddy badge maker. Template management, image "
        "compositing, and print-accurate PDF/PNG export at exact mm sizes."
    ),
    lifespan=lifespan,
    debug=DEBUG,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)


@app.middleware("http")
async def request_context(request: Request, call_next):
    """Attach a request id and log slow/failed calls — renders are seconds long."""
    rid = uuid.uuid4().hex[:8]
    started = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        log.exception("[%s] %s %s failed", rid, request.method, request.url.path)
        raise
    elapsed = (time.perf_counter() - started) * 1000
    if elapsed > 1000 or response.status_code >= 400:
        log.info(
            "[%s] %s %s -> %d (%.0f ms)",
            rid,
            request.method,
            request.url.path,
            response.status_code,
            elapsed,
        )
    response.headers["X-Request-ID"] = rid
    return response


@app.exception_handler(RequestValidationError)
async def validation_handler(request: Request, exc: RequestValidationError):
    """Turn pydantic's nested errors into one sentence a user can act on."""
    first = exc.errors()[0] if exc.errors() else {}
    field = ".".join(str(p) for p in first.get("loc", [])[1:]) or "request"
    raise_detail = f"{field}: {first.get('msg', 'is invalid')}"
    log.warning("validation failed on %s: %s", request.url.path, exc.errors())
    return JSONResponse(status_code=422, content={"detail": raise_detail})


@app.exception_handler(Exception)
async def unhandled_handler(request: Request, exc: Exception):
    rid = uuid.uuid4().hex[:8]
    log.exception("[%s] unhandled error on %s", rid, request.url.path)
    return JSONResponse(
        status_code=500,
        content={
            "detail": "Something went wrong on the server. "
            f"Quote reference {rid} if you report this.",
            "reference": rid,
        },
    )


class CachedStatic(StaticFiles):
    """
    Serve uploads with `nosniff` so a file can never be interpreted as HTML,
    and with a short cache so versioned URLs (?v=N) stay cheap.
    """

    def file_response(self, *args, **kwargs):
        resp = super().file_response(*args, **kwargs)
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["Cache-Control"] = "public, max-age=60"
        return resp


app.mount("/uploads", CachedStatic(directory=UPLOAD_DIR), name="uploads")

for r in (templates, sessions, render, export, layout):
    app.include_router(r.router, prefix="/api")


@app.get("/api/health")
def health():
    """Real health: a bad database must not report healthy."""
    db_ok = healthcheck()
    uploads_ok = os.access(UPLOAD_DIR, os.W_OK)
    ok = db_ok and uploads_ok
    return JSONResponse(
        status_code=200 if ok else 503,
        content={
            "status": "ok" if ok else "degraded",
            "service": "button-buddy-api",
            "database": db_ok,
            "uploads_writable": uploads_ok,
            "print_dpi": PRINT_DPI,
        },
    )
