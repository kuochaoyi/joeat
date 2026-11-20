"""SQLAlchemy engine / session factory."""
from collections.abc import Iterator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings

_engine = None
_SessionLocal = None


def get_engine():
    global _engine, _SessionLocal
    if _engine is None:
        _engine = create_engine(get_settings().database_url, pool_pre_ping=True, future=True)
        _SessionLocal = sessionmaker(bind=_engine, expire_on_commit=False, future=True)
    return _engine


def reset_engine() -> None:
    """Used by tests that switch DATABASE_URL."""
    global _engine, _SessionLocal
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _SessionLocal = None


def new_session() -> Session:
    get_engine()
    return _SessionLocal()  # type: ignore[misc]


def apply_runtime_flags(db: Session) -> None:
    """Per-transaction switches read by the schema's views (see schema_v2.sql: joeat.allow_test_evidence)."""
    flag = "on" if get_settings().allow_test_evidence else "off"
    db.execute(text("SELECT set_config('joeat.allow_test_evidence', :v, true)"), {"v": flag})


def get_db() -> Iterator[Session]:
    db = new_session()
    try:
        yield db
    finally:
        db.close()
