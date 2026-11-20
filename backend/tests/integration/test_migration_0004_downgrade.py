"""Downgrading 0004 (demo isolation) after a reviewer superseded third-party evidence with a DEMO declaration.

Regression: the downgrade deleted the demo evidence while the superseded row still pointed at it (superseded_by foreign key), so `alembic downgrade`
failed. It must give the superseded evidence its status back instead. Own module: it downgrades the module's scratch database.
"""
import psycopg
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text

from app.core.config import get_settings
from app.services import merchant as svc
from tests.conftest import BACKEND
from tests.integration._merchant_helpers import CALL_NOTE, H, rid

pytestmark = pytest.mark.integration


def test_downgrade_0004_restores_evidence_that_a_demo_declaration_superseded(merchant_env, client, db, monkeypatch):
    monkeypatch.setenv("ALLOW_TEST_EVIDENCE", "true")
    get_settings.cache_clear()
    try:
        claim = client.post("/ops/claims", json={"restaurant_id": str(rid(db, "郭家肉粽")), "is_demo": True}, headers=H).json()["claim_id"]
        assert client.post(f"/ops/claims/{claim}/verify", json={"method": "phone_callback", "note": CALL_NOTE, "claimant_role": "owner"}, headers=H).status_code == 200
        d = svc.start_declaration(db, "merchant-ui", claim)
        svc.set_item(db, "merchant-ui", d, "peanut", "absent_entire_menu", cross_contact_status="confirmed_none", note=None)
        svc.set_menu(db, "merchant-ui", d, "https://example.invalid/demo.pdf")
        svc.submit_declaration(db, "merchant-ui", d, "owner", db.scalar(text("SELECT ref.today_tpe()")), "attest-v1")
        r = client.post(f"/ops/declarations/{d}/publish", json={"supersede": True}, headers=H)
        assert r.status_code == 200, r.text
    finally:
        get_settings.cache_clear()
    dsn = merchant_env.replace("postgresql+psycopg://", "postgresql://")

    def q(sql):
        with psycopg.connect(dsn) as conn:
            return conn.execute(sql).fetchall()

    third_party = "SELECT status FROM enrichment.restaurant_attribute_evidence e JOIN ref.data_source s USING (source_id) WHERE s.source_type <> 'test_fixture' AND e.attribute_code = 'peanut' AND e.restaurant_id = '{}'"
    assert ("superseded",) in q(third_party.format(rid(db, "郭家肉粽")))                       # precondition: the demo declaration really superseded it
    db.close()
    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "alembic"))
    command.downgrade(cfg, "0003")                                                          # used to fail on the superseded_by foreign key
    assert q("SELECT count(*) FROM enrichment.restaurant_attribute_evidence e JOIN ref.data_source s USING (source_id) WHERE s.source_type = 'test_fixture' AND e.declaration_id IS NOT NULL") == [(0,)]
    assert q(third_party.format(rid(db, "郭家肉粽"))) == [("active",)] * len(q(third_party.format(rid(db, "郭家肉粽"))))
    command.upgrade(cfg, "head")
