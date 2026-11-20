"""Alembic: upgrade -> downgrade -> upgrade on a scratch database (never touches the shared test database)."""
import re
from pathlib import Path

import psycopg
import pytest
from alembic import command
from alembic.config import Config

pytestmark = pytest.mark.integration
BACKEND = Path(__file__).resolve().parents[2]


def test_migrations_round_trip(database_url, monkeypatch):
    from app.core.config import get_settings
    from app.db.session import reset_engine

    name = "joeat_migration_scratch"
    admin = re.sub(r"/[^/]+$", "/postgres", database_url.replace("postgresql+psycopg://", "postgresql://"))
    scratch = re.sub(r"/[^/]+$", f"/{name}", database_url)
    with psycopg.connect(admin, autocommit=True) as c:
        c.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
        c.execute(f"CREATE DATABASE \"{name}\" ENCODING 'UTF8' TEMPLATE template0")
    try:
        monkeypatch.setenv("DATABASE_URL", scratch)
        get_settings.cache_clear()
        reset_engine()
        cfg = Config(str(BACKEND / "alembic.ini"))
        cfg.set_main_option("script_location", str(BACKEND / "alembic"))

        def tables():
            with psycopg.connect(scratch.replace("postgresql+psycopg://", "postgresql://")) as conn:
                return {r[0] for r in conn.execute("SELECT schemaname || '.' || tablename FROM pg_tables WHERE schemaname IN ('ref','staging','identity','enrichment','product')")}

        command.upgrade(cfg, "head")
        up = tables()
        assert len(up) == 36 and {"identity.restaurant", "product.recommendation_candidate", "product.restaurant_report"} <= up       # 30 + the report queue (0005) + time poll and vote tables (0008)
        with psycopg.connect(scratch.replace("postgresql+psycopg://", "postgresql://")) as conn:
            cols = {r[0] for r in conn.execute("SELECT column_name FROM information_schema.columns WHERE table_schema='product' AND table_name IN ('dining_session','participant')")}
        assert {"title", "location_label", "constraints_submitted_at", "preferences_submitted_at", "strict_allergy"} <= cols
        command.downgrade(cfg, "base")
        assert tables() == set()
        command.upgrade(cfg, "head")
        assert tables() == up
    finally:
        monkeypatch.setenv("DATABASE_URL", database_url)
        get_settings.cache_clear()
        reset_engine()
        with psycopg.connect(admin, autocommit=True) as c:
            c.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')


def test_migration_0003_downgrade_restores_the_previous_views_and_upgrade_works_again(database_url, monkeypatch):
    """0003 changes a view and adds columns; going back to 0002 must leave a working schema (and first-party evidence is removed with it)."""
    from app.core.config import get_settings
    from app.db.session import reset_engine

    name = "joeat_migration_scratch_0003"
    admin = re.sub(r"/[^/]+$", "/postgres", database_url.replace("postgresql+psycopg://", "postgresql://"))
    scratch = re.sub(r"/[^/]+$", f"/{name}", database_url)
    with psycopg.connect(admin, autocommit=True) as c:
        c.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
        c.execute(f"CREATE DATABASE \"{name}\" ENCODING 'UTF8' TEMPLATE template0")
    try:
        monkeypatch.setenv("DATABASE_URL", scratch)
        get_settings.cache_clear()
        reset_engine()
        cfg = Config(str(BACKEND / "alembic.ini"))
        cfg.set_main_option("script_location", str(BACKEND / "alembic"))
        dsn = scratch.replace("postgresql+psycopg://", "postgresql://")

        def q(sql):
            with psycopg.connect(dsn) as conn:
                return conn.execute(sql).fetchall()

        command.upgrade(cfg, "head")
        assert {r[0] for r in q("SELECT table_name FROM information_schema.tables WHERE table_schema = 'merchant'")} == {"claim", "declaration", "declaration_item", "declaration_audit", "incident_report"}
        evidence_cols = {r[0] for r in q("SELECT column_name FROM information_schema.columns WHERE table_schema='enrichment' AND table_name='restaurant_attribute_evidence'")}
        assert {"status", "superseded_by", "declaration_id", "suspended_by_incident", "cross_contact_status", "presence_extent"} <= evidence_cols
        command.downgrade(cfg, "0002")
        assert q("SELECT table_name FROM information_schema.tables WHERE table_schema = 'merchant'") == []
        evidence_cols = {r[0] for r in q("SELECT column_name FROM information_schema.columns WHERE table_schema='enrichment' AND table_name='restaurant_attribute_evidence'")}
        assert not {"status", "declaration_id", "presence_extent"} & evidence_cols
        # the three views that were rebuilt are queryable again
        for view in ("v_evidence_valid", "v_evidence_expanded", "restaurant_attribute_state"):
            assert q(f"SELECT count(*) FROM enrichment.{view}") == [(0,)]
        assert q("SELECT count(*) FROM information_schema.columns WHERE table_schema='ref' AND table_name='attribute' AND column_name='default_constraint_class'") == [(0,)]
        command.upgrade(cfg, "head")
        assert q("SELECT count(*) FROM information_schema.tables WHERE table_schema = 'merchant'") == [(5,)]
    finally:
        monkeypatch.setenv("DATABASE_URL", database_url)
        get_settings.cache_clear()
        reset_engine()
        with psycopg.connect(admin, autocommit=True) as c:
            c.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
