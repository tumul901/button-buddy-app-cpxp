"""
Housekeeping.

Sessions hold user photos. Nothing deleted them in v1, so the uploads
directory grew without bound and held personal photos indefinitely — both a
disk problem and a privacy one. This sweeps rows and their files together.
"""

import logging
from datetime import datetime, timedelta, timezone

from sqlmodel import Session, select

from app.database import engine
from app.models.session import BadgeSession
from app.services import storage

log = logging.getLogger(__name__)


def sweep_expired_sessions(ttl_hours: int) -> int:
    """Delete sessions untouched for `ttl_hours`. Returns how many went."""
    if ttl_hours <= 0:
        return 0

    cutoff = datetime.now(timezone.utc) - timedelta(hours=ttl_hours)
    removed = 0
    try:
        with Session(engine) as db:
            rows = db.exec(select(BadgeSession)).all()
            for row in rows:
                stamp = row.updated_at or row.created_at
                if stamp is None:
                    continue
                # Rows written before the timezone-aware switch are naive.
                if stamp.tzinfo is None:
                    stamp = stamp.replace(tzinfo=timezone.utc)
                if stamp < cutoff:
                    db.delete(row)
                    storage.remove_session_dir(row.id)
                    removed += 1
            if removed:
                db.commit()
    except Exception as exc:  # never let housekeeping break startup
        log.warning("session sweep failed: %s", exc)
        return 0
    return removed
