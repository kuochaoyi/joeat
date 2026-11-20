"""Integration-test fixtures.

A throw-away database `joeat_test` is created next to the configured one (same server), migrated with Alembic and seeded with
data/seed/*.sql. If no PostgreSQL is reachable, integration tests are skipped with a message (unit tests never need a database).
Override with JOEAT_TEST_DATABASE_URL (postgresql+psycopg://user:pass@host:port/dbname - the database is DROPPED and recreated).
"""
from __future__ import annotations

import os
import re
import uuid
from pathlib import Path

import psycopg
import pytest
from alembic import command
from alembic.config import Config

BACKEND = Path(__file__).resolve().parents[1]
SEED_DIR = BACKEND.parent / "data" / "seed"

# The dev backend/.env turns ALLOW_TEST_EVIDENCE on for the demo; the tests assume the production default (fixtures hidden) and opt in explicitly.
os.environ["ALLOW_TEST_EVIDENCE"] = "false"


def _test_url() -> str:
    explicit = os.environ.get("JOEAT_TEST_DATABASE_URL")
    if explicit:
        return explicit
    from app.core.config import get_settings
    get_settings.cache_clear()
    base = get_settings().database_url
    return re.sub(r"/[^/]+$", "/joeat_test", base)


def _admin_dsn(url: str) -> str:
    return re.sub(r"/[^/]+$", "/postgres", url.replace("postgresql+psycopg://", "postgresql://"))


@pytest.fixture(scope="session")
def database_url():
    url = _test_url()
    name = url.rsplit("/", 1)[1]
    try:
        admin = psycopg.connect(_admin_dsn(url), autocommit=True, connect_timeout=5)
    except Exception as exc:  # no database -> skip, do not fail
        pytest.skip(f"PostgreSQL not reachable ({exc.__class__.__name__}); see TESTING.md", allow_module_level=False)
    with admin:
        admin.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
        admin.execute(f"CREATE DATABASE \"{name}\" ENCODING 'UTF8' TEMPLATE template0")
    os.environ["DATABASE_URL"] = url
    from app.core.config import get_settings
    from app.db.session import reset_engine
    get_settings.cache_clear()
    reset_engine()
    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "alembic"))
    command.upgrade(cfg, "head")
    with psycopg.connect(url.replace("postgresql+psycopg://", "postgresql://"), autocommit=True) as conn:
        for f in sorted(SEED_DIR.glob("*.sql")):
            conn.execute(f.read_text(encoding="utf-8"))
    yield url
    reset_engine()
    with psycopg.connect(_admin_dsn(url), autocommit=True) as admin:
        admin.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')


@pytest.fixture()
def db(database_url):
    from app.db.session import new_session
    s = new_session()
    try:
        yield s
    finally:
        s.close()


@pytest.fixture()
def client(database_url):
    from fastapi.testclient import TestClient

    from app.main import create_app
    return TestClient(create_app())


@pytest.fixture()
def uniq() -> str:
    """Unique prefix so every test uses its own LINE user ids (the database is shared within the run)."""
    return "t-" + uuid.uuid4().hex[:8]


@pytest.fixture(scope="module")
def merchant_env(database_url):
    """A fresh migrated+seeded database just for this module; the environment is restored afterwards."""
    import os

    from app.core.config import get_settings
    from app.db.session import reset_engine
    name = "joeat_test_merchant"
    admin = re.sub(r"/[^/]+$", "/postgres", database_url.replace("postgresql+psycopg://", "postgresql://"))
    url = re.sub(r"/[^/]+$", f"/{name}", database_url)
    with psycopg.connect(admin, autocommit=True) as c:
        c.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
        c.execute(f"CREATE DATABASE \"{name}\" ENCODING 'UTF8' TEMPLATE template0")
    saved = {k: os.environ.get(k) for k in ("DATABASE_URL", "OPS_API_KEY")}
    os.environ["DATABASE_URL"], os.environ["OPS_API_KEY"] = url, "test-ops-key"
    get_settings.cache_clear()
    reset_engine()
    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "alembic"))
    command.upgrade(cfg, "head")
    with psycopg.connect(url.replace("postgresql+psycopg://", "postgresql://"), autocommit=True) as conn:
        for f in sorted(SEED_DIR.glob("*.sql")):
            conn.execute(f.read_text(encoding="utf-8"))
    yield url
    for k, v in saved.items():
        os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v)
    get_settings.cache_clear()
    reset_engine()
    with psycopg.connect(admin, autocommit=True) as c:
        c.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')


