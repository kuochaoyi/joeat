"""Pilot safeguards that touch the database: the pre-flight's database checks, and seed.py refusing to wipe real merchant data."""
import importlib.util
import sys

import pytest
from sqlalchemy import text

from app.core.preflight import check_database
from tests.conftest import BACKEND
from tests.integration._merchant_helpers import H, rid, verified_claim

pytestmark = pytest.mark.integration


@pytest.fixture()
def env(merchant_env, client, db):
    return client, db


def by_name(results):
    return {name: (level, msg) for level, name, msg in results}


def load_seed_script():
    spec = importlib.util.spec_from_file_location("seed_script", BACKEND / "scripts" / "seed.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_preflight_database_checks_see_demo_data_fixtures_and_real_claims(env, monkeypatch):
    from app.core.config import get_settings
    client, db = env
    r = by_name(check_database(db))
    assert r["migrations"][0] == "OK" and r["demo_data"][0] == "OK" and r["claims"][1].endswith("0 invited, 0 verified")
    assert r["seed_fixtures"][0] == "WARN"                                                  # the seed's hidden test claims are still in a freshly seeded database
    verified_claim(client, db, "鴨肉珍")                                                    # a REAL claim
    assert "1 verified" in by_name(check_database(db))["claims"][1]
    monkeypatch.setenv("ALLOW_TEST_EVIDENCE", "true")
    get_settings.cache_clear()
    try:
        demo = client.post("/ops/claims", json={"restaurant_id": str(rid(db, "東京小城")), "is_demo": True}, headers=H)
        assert demo.status_code == 201
    finally:
        get_settings.cache_clear()
    assert by_name(check_database(db))["demo_data"][0] == "FAIL"                           # demo data must never be in the pilot database


def test_seed_reset_refuses_to_delete_real_merchant_claims(env, monkeypatch, capsys):
    client, db = env
    claims_before = db.scalar(text("SELECT count(*) FROM merchant.claim WHERE NOT is_demo"))
    assert claims_before >= 1                                                               # the previous test created one (module-scoped database)
    seed = load_seed_script()
    monkeypatch.setattr(sys, "argv", ["seed.py", "--reset"])
    assert seed.main() == 2
    assert "refusing --reset" in capsys.readouterr().out
    db.rollback()
    assert db.scalar(text("SELECT count(*) FROM merchant.claim WHERE NOT is_demo")) == claims_before     # nothing was touched
    assert db.scalar(text("SELECT count(*) FROM identity.restaurant")) == 31
