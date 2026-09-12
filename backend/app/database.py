import logging

from sqlalchemy import event, text
from sqlmodel import Session, SQLModel, create_engine

from app.config import DATABASE_URL

log = logging.getLogger(__name__)

is_sqlite = DATABASE_URL.startswith("sqlite")

connect_args = {"check_same_thread": False, "timeout": 15} if is_sqlite else {}

engine = create_engine(
    DATABASE_URL,
    echo=False,
    connect_args=connect_args,
    pool_pre_ping=not is_sqlite,
)

if is_sqlite:

    @event.listens_for(engine, "connect")
    def _sqlite_pragmas(dbapi_conn, _record):
        """
        WAL lets readers proceed during a write, which matters here because a
        render holds the request open for a second or more while Pillow works.
        Without it concurrent renders hit 'database is locked'.
        """
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA synchronous=NORMAL")
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()


def create_db_and_tables() -> None:
    # Import models so their tables are registered on SQLModel.metadata.
    from app.models import session as _session  # noqa: F401
    from app.models import template as _template  # noqa: F401

    SQLModel.metadata.create_all(engine)


def healthcheck() -> bool:
    try:
        with Session(engine) as s:
            s.exec(text("SELECT 1"))
        return True
    except Exception as exc:  # pragma: no cover - depends on external db
        log.error("database healthcheck failed: %s", exc)
        return False


def get_session():
    with Session(engine) as session:
        yield session
