"""
Schema compatibility guard.

There is no migration framework here yet (see ROBUSTNESS_REVIEW.md P2-8), and
`SQLModel.metadata.create_all` only ever *creates* — it never alters an
existing table. So a database written by an older build keeps its old columns
and every query fails at runtime with a raw `no such column` error, long after
startup reported success.

This module detects that case up front and handles it honestly:

  * SQLite  — archive the old file next to itself (nothing is deleted) and
              start clean, logging exactly what happened and where it went.
  * Others  — refuse to start, naming the mismatch, because silently moving a
              production database is never the right call.
"""

import logging
import os
import shutil
import time

from sqlalchemy import inspect

from app.database import engine, is_sqlite

log = logging.getLogger(__name__)

# Columns this build requires, by table.
REQUIRED = {
    "templates": {"file_key", "thumbnail_key"},
    "badge_sessions": {"photo_key", "composite_key", "render_version"},
}


class IncompatibleSchema(RuntimeError):
    pass


def _missing_columns() -> dict[str, set[str]]:
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    missing: dict[str, set[str]] = {}

    for table, required in REQUIRED.items():
        if table not in existing_tables:
            continue  # not created yet; create_all will make it correctly
        columns = {c["name"] for c in inspector.get_columns(table)}
        absent = required - columns
        if absent:
            missing[table] = absent
    return missing


def _sqlite_path() -> str | None:
    url = str(engine.url)
    if "sqlite" not in url:
        return None
    path = engine.url.database
    return os.path.abspath(path) if path and path != ":memory:" else None


def ensure_compatible_schema() -> bool:
    """
    Returns True when the database was archived and recreated, False when it
    was already fine. Raises IncompatibleSchema for non-SQLite mismatches.
    """
    missing = _missing_columns()
    if not missing:
        return False

    summary = "; ".join(f"{t} is missing {', '.join(sorted(c))}" for t, c in missing.items())

    if not is_sqlite:
        raise IncompatibleSchema(
            f"The database schema is from an older Button Buddy build ({summary}). "
            "Back it up and migrate it before starting this version."
        )

    path = _sqlite_path()
    if not path or not os.path.exists(path):
        return False

    engine.dispose()  # release the file before moving it
    stamp = time.strftime("%Y%m%d-%H%M%S")
    archive = f"{path}.legacy-{stamp}"

    try:
        shutil.move(path, archive)
        # WAL sidecars belong to the archived database, not the new one.
        for suffix in ("-wal", "-shm"):
            side = path + suffix
            if os.path.exists(side):
                try:
                    os.remove(side)
                except OSError:
                    pass
    except OSError as exc:
        raise IncompatibleSchema(
            f"The database schema is from an older build ({summary}) and it could not be "
            f"archived automatically ({exc}). Stop any other process using "
            f"{os.path.basename(path)} and try again."
        ) from exc

    log.warning(
        "Database schema was from an older build (%s). "
        "The old file has been archived to %s and a fresh database created. "
        "Previous sessions and templates are not carried over.",
        summary,
        os.path.basename(archive),
    )
    return True
