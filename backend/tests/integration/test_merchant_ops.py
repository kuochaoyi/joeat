"""Reviewer API + declaration lifecycle, end to end through the real recommendation engine.

Runs on its OWN scratch database (fixture `merchant_env` in conftest.py): the shared test database must stay free of first-party evidence, other tests assert that.
"""
import uuid

import pytest
from sqlalchemy import text

from app.services import merchant as svc
from tests.integration._merchant_helpers import CALL_NOTE, H, H2, engine, rid, state, submitted_declaration, verified_claim

pytestmark = pytest.mark.integration


@pytest.fixture()
def env(merchant_env, client, db):
    return client, db


# ------------------------------------------------------------------ access control
def test_ops_api_is_disabled_without_a_key_and_checks_key_and_user(merchant_env, client, monkeypatch):
    from app.core.config import get_settings
    assert client.get("/ops/declarations").status_code == 401                                              # no key sent
    assert client.get("/ops/declarations", headers={"X-Ops-Key": "wrong", "X-Ops-User": "x1"}).status_code == 401
    assert client.get("/ops/declarations", headers={"X-Ops-Key": "test-ops-key"}).json()["error"] == "ops_user_required"
    assert client.get("/ops/declarations", headers=H).status_code == 200
    # the browser percent-encodes a Chinese reviewer name (headers are ASCII); the audit trail must get the real name
    from urllib.parse import quote
    assert client.get("/ops/declarations", headers={"X-Ops-Key": "test-ops-key", "X-Ops-User": quote("審核員小明")}).status_code == 200
    assert client.get("/ops/declarations", headers={"X-Ops-Key": "test-ops-key", "X-Ops-User": quote("a")}).json()["error"] == "ops_user_required"
    monkeypatch.setenv("OPS_API_KEY", "")
    get_settings.cache_clear()
    try:
        r = client.get("/ops/declarations", headers=H)
        assert r.status_code == 503 and r.json()["error"] == "ops_disabled"
    finally:
        monkeypatch.setenv("OPS_API_KEY", "test-ops-key")
        get_settings.cache_clear()


# ------------------------------------------------------------------ claims and verification
def test_invite_token_is_shown_once_and_only_its_hash_is_stored(env):
    client, db = env
    r = client.post("/ops/claims", json={"restaurant_id": str(rid(db, "鴨肉珍"))}, headers=H).json()
    token = r["token"]
    stored = db.scalar(text("SELECT token_hash FROM merchant.claim WHERE claim_id = :c"), {"c": r["claim_id"]})
    assert stored == svc.hash_token(token) and token not in stored and len(stored) == 64
    assert "token" not in client.get(f"/ops/claims/{r['claim_id']}", headers=H).json()
    assert client.post("/ops/claims", json={"restaurant_id": str(uuid.uuid4())}, headers=H).status_code == 404


@pytest.mark.parametrize("method,level", [("phone_callback", "strong"), ("onsite_visit", "strong"), ("official_menu_review", "strong"), ("official_channel_message", "basic")])
def test_verification_level_follows_the_method_and_records_who_when_how(env, method, level):
    client, db = env
    cid = verified_claim(client, db, "老蔡虱目魚粥", method=method)
    c = client.get(f"/ops/claims/{cid}", headers=H).json()
    assert c["verification_level"] == level and c["verification_method"] == method
    assert c["verified_by"] == "reviewer-a" and c["verified_at"] and c["verification_note"] == CALL_NOTE and c["status"] == "verified"


def test_verification_needs_a_real_note_a_known_method_and_cannot_be_repeated(env):
    client, db = env
    cid = client.post("/ops/claims", json={"restaurant_id": str(rid(db, "鴨肉珍"))}, headers=H).json()["claim_id"]
    assert client.post(f"/ops/claims/{cid}/verify", json={"method": "phone_callback", "note": "ok"}, headers=H).status_code == 422       # note too short
    assert client.post(f"/ops/claims/{cid}/verify", json={"method": "operator_known", "note": CALL_NOTE}, headers=H).status_code == 422   # no longer an accepted method
    assert client.post(f"/ops/claims/{cid}/verify", json={"method": "phone_callback", "note": CALL_NOTE}, headers=H).status_code == 200
    again = client.post(f"/ops/claims/{cid}/verify", json={"method": "onsite_visit", "note": CALL_NOTE}, headers=H)
    assert again.status_code == 409 and again.json()["error"] == "rule_violation"
    assert client.post(f"/ops/claims/{cid}/revoke", headers=H).json()["status"] == "revoked"
    assert client.post(f"/ops/claims/{cid}/revoke", headers=H).status_code == 409


def test_the_database_itself_refuses_a_level_that_does_not_match_the_method(env):
    client, db = env
    cid = client.post("/ops/claims", json={"restaurant_id": str(rid(db, "鴨肉珍"))}, headers=H).json()["claim_id"]
    with pytest.raises(Exception, match="claim_level_matches_method"):
        db.execute(text("UPDATE merchant.claim SET status='verified', verification_method='official_channel_message', verification_level='strong', "
                        "verified_by='x', verified_at=now(), verification_note='some note here' WHERE claim_id=:c"), {"c": cid})
    db.rollback()
    with pytest.raises(Exception, match="claim_verified_needs_proof"):
        db.execute(text("UPDATE merchant.claim SET status='verified', verification_method='phone_callback', verification_level='strong', verified_by='x', verified_at=now() WHERE claim_id=:c"), {"c": cid})
    db.rollback()


def test_an_unverified_claim_cannot_declare(env):
    client, db = env
    cid = client.post("/ops/claims", json={"restaurant_id": str(rid(db, "鴨肉珍"))}, headers=H).json()["claim_id"]
    with pytest.raises(Exception, match="only a verified claim"):
        svc.start_declaration(db, "merchant-ui", cid)
    db.rollback()


# ------------------------------------------------------------------ the full path: declaration -> review -> evidence -> recommendation
def test_full_lifecycle_strong_claim_with_no_shared_equipment_gives_a_confirmed_claim_the_engine_can_use(env):
    client, db = env
    cid, d = submitted_declaration(client, db, "鴨肉珍", {"peanut": ("absent_entire_menu", "confirmed_none"), "beef": "present_in_most_dishes"}, menu="https://example.invalid/menu.pdf")
    queue = client.get("/ops/declarations", params={"status": "submitted"}, headers=H).json()["declarations"]
    mine = next(x for x in queue if x["declaration_id"] == d)
    assert mine["restaurant"] == "鴨肉珍" and mine["verification_level"] == "strong" and mine["answered_items"] == 2 and mine["conflict_count"] == 0

    detail = client.get(f"/ops/declarations/{d}", headers=H).json()
    plan = {p["attribute_code"]: p for p in detail["plan"]}
    assert plan["peanut"]["new_state"] == "CONFIRMED_ABSENT" and plan["peanut"]["evidence_basis"] == "official_menu" and plan["peanut"]["confidence"] == "HIGH"
    assert plan["beef"]["new_state"] == "CONFIRMED_PRESENT" and plan["beef"]["presence_extent"] == "most"
    assert detail["claim"]["verified_by"] == "reviewer-a" and detail["conflicts"] == []
    assert state(db, "鴨肉珍", "peanut") == "UNKNOWN", "nothing is evidence until a reviewer publishes it"

    r = client.post(f"/ops/declarations/{d}/publish", headers=H2)
    assert r.status_code == 200 and r.json()["published_evidence"] == 2 and r.json()["declaration"]["status"] == "approved"
    assert r.json()["declaration"]["reviewed_by"] == "reviewer-b"
    ev = db.execute(text("SELECT state::text, evidence_basis, confidence, applies_to, cross_contact_status, presence_extent, valid_until - last_verified_at AS days, evidence_text, declaration_id "
                         "FROM enrichment.restaurant_attribute_evidence WHERE restaurant_id = :r AND attribute_code = 'peanut' AND declaration_id = :d"), {"r": rid(db, "鴨肉珍"), "d": d}).one()
    assert ev[:7] == ("CONFIRMED_ABSENT", "official_menu", "HIGH", "this_branch", "confirmed_none", None, 90)
    assert all(x in ev[7] for x in ("phone_callback", "聲明日", "共用設備：確認無共用")), ev[7]                  # how it was verified, and when the merchant declared, are inside the evidence text
    assert "reviewer-a" not in ev[7], "the verifier's name must not be in the text (the public restaurant-detail endpoint returns it)"
    who = db.scalar(text("SELECT c.verified_by FROM enrichment.restaurant_attribute_evidence e JOIN merchant.declaration d USING (declaration_id) JOIN merchant.claim c USING (claim_id) WHERE e.declaration_id = :d LIMIT 1"), {"d": ev[8]})
    assert who == "reviewer-a", "who verified is still traceable: evidence -> declaration -> claim"
    assert [e["event"] for e in client.get(f"/ops/declarations/{d}", headers=H).json()["audit"]] == ["status:draft", "status:submitted", "status:approved"]

    row, resp = engine(client, db, "鴨肉珍", "peanut")
    assert row == ("CONFIRMED_ABSENT", "PASS", "none", True, "official_menu")
    card = next((t for t in resp["top3"] if t["name"] == "鴨肉珍"), None)
    assert card is None or card["hard_constraint"]["confirmed_safe"] == ["花生"]


@pytest.mark.parametrize("cross,expected_state,expected_action,level,safe", [
    ("confirmed_none", "CONFIRMED_ABSENT", "PASS", "none", True),
    ("possible", "LIKELY_ABSENT", "WARN", "critical", False),
    ("unknown", "LIKELY_ABSENT", "WARN", "critical", False),
    ("confirmed_shared", "LIKELY_PRESENT", "EXCLUDE", "none", False)])
def test_shared_equipment_decides_how_far_a_critical_allergen_claim_can_go(env, cross, expected_state, expected_action, level, safe):
    client, db = env
    cid, d = submitted_declaration(client, db, "阿英排骨飯", {"sesame": ("absent_entire_menu", cross)})
    plan = client.get(f"/ops/declarations/{d}", headers=H).json()["plan"][0]
    assert plan["new_state"] == expected_state and plan["capped_by_cross_contact"] == (cross != "confirmed_none")
    client.post(f"/ops/declarations/{d}/publish", headers=H)
    row, _ = engine(client, db, "阿英排骨飯", "sesame")
    assert row[:4] == (expected_state, expected_action, level, safe), row


def test_shared_equipment_does_not_cap_a_non_critical_attribute(env):
    client, db = env
    cid, d = submitted_declaration(client, db, "里歐歐式早餐(五福四路131號)", {"pork": ("absent_entire_menu", "unknown")})
    assert client.get(f"/ops/declarations/{d}", headers=H).json()["plan"][0]["new_state"] == "CONFIRMED_ABSENT"      # pork is high, not critical: stored, not capped


def test_a_weakly_verified_claim_can_never_become_confirmed(env):
    client, db = env
    cid, d = submitted_declaration(client, db, "田記豆漿", {"peanut": ("absent_entire_menu", "confirmed_none")}, method="official_channel_message")
    plan = client.get(f"/ops/declarations/{d}", headers=H).json()["plan"][0]
    assert plan["new_state"] == "LIKELY_ABSENT" and plan["confidence"] == "MEDIUM"
    client.post(f"/ops/declarations/{d}/publish", headers=H)
    row, _ = engine(client, db, "田記豆漿", "peanut")
    assert row[:4] == ("LIKELY_ABSENT", "WARN", "critical", False)


def test_official_menu_review_requires_the_menu_at_publish_time(env):
    client, db = env
    cid, d = submitted_declaration(client, db, "大智羊肉", {"egg": "absent_entire_menu"}, method="official_menu_review")
    r = client.post(f"/ops/declarations/{d}/publish", headers=H)
    assert r.status_code == 409 and "official_menu_review" in r.json()["message"]
    cid2, d2 = submitted_declaration(client, db, "大智羊肉", {"egg": "absent_entire_menu"}, method="official_menu_review", menu="https://example.invalid/m.pdf")
    assert client.post(f"/ops/declarations/{d2}/publish", headers=H).status_code == 200


# ------------------------------------------------------------------ contradictions: never resolved silently
def test_contradiction_with_likely_evidence_needs_an_explicit_supersede(env):
    client, db = env
    cid, d = submitted_declaration(client, db, "郭家肉粽", {"peanut": ("absent_entire_menu", "confirmed_none")})
    detail = client.get(f"/ops/declarations/{d}", headers=H).json()
    assert detail["plan"][0]["conflicts"] and detail["plan"][0]["conflicts_confirmed"] is False
    assert detail["conflicts"][0]["state"] == "LIKELY_PRESENT" and "土豆" in detail["conflicts"][0]["evidence_text"]
    listed = next(x for x in client.get("/ops/declarations", params={"status": "submitted"}, headers=H).json()["declarations"] if x["declaration_id"] == d)
    assert listed["conflict_count"] == 1 and listed["restaurant"] == "郭家肉粽"
    blocked = client.post(f"/ops/declarations/{d}/publish", headers=H)
    assert blocked.status_code == 409 and "contradiction" in blocked.json()["message"] and state(db, "郭家肉粽", "peanut") == "LIKELY_PRESENT"
    ok = client.post(f"/ops/declarations/{d}/publish", json={"supersede": True}, headers=H2)
    assert ok.status_code == 200 and state(db, "郭家肉粽", "peanut") == "CONFIRMED_ABSENT"
    audit = client.get(f"/ops/declarations/{d}", headers=H).json()["audit"]
    assert any(a["event"] == "superseded_third_party_evidence" and a["actor"] == "reviewer-b" for a in audit)


def test_a_declaration_can_never_override_confirmed_evidence(env):
    client, db = env
    cid, d = submitted_declaration(client, db, "港園牛肉麵", {"beef": "absent_entire_menu"})          # the restaurant name itself confirms beef
    assert client.get(f"/ops/declarations/{d}", headers=H).json()["plan"][0]["conflicts_confirmed"] is True
    r = client.post(f"/ops/declarations/{d}/publish", json={"supersede": True}, headers=H)
    assert r.status_code == 409 and "CONFIRMED" in r.json()["message"] and state(db, "港園牛肉麵", "beef") == "CONFIRMED_PRESENT"


# ------------------------------------------------------------------ review outcomes
def test_reject_and_needs_info_require_a_note_and_needs_info_reopens_the_items(env):
    client, db = env
    cid, d = submitted_declaration(client, db, "小韓國", {"gluten": "absent_entire_menu"})
    assert client.post(f"/ops/declarations/{d}/reject", json={"note": "no"}, headers=H).status_code == 422
    r = client.post(f"/ops/declarations/{d}/needs-info", json={"note": "請附上最新菜單照片"}, headers=H)
    assert r.json()["status"] == "needs_info" and r.json()["review_note"] == "請附上最新菜單照片" and r.json()["reviewed_by"] == "reviewer-a"
    svc.set_item(db, "merchant-ui", d, "gluten", "present_in_some_dishes")                        # frozen while submitted, editable again after needs_info
    svc.set_menu(db, "merchant-ui", d, "https://example.invalid/m2.pdf")
    svc.submit_declaration(db, "merchant-ui", d, "owner", db.scalar(text("SELECT ref.today_tpe()")), "attest-v1")
    assert client.post(f"/ops/declarations/{d}/reject", json={"note": "菜單與聲明不符"}, headers=H).json()["status"] == "rejected"
    assert client.post(f"/ops/declarations/{d}/publish", headers=H).status_code == 409           # a rejected declaration cannot be published
    assert state(db, "小韓國", "gluten") == "UNKNOWN"


def test_submitted_items_are_frozen_and_declarations_are_never_deleted(env):
    client, db = env
    cid, d = submitted_declaration(client, db, "鹽埕町冰果室", {"milk": "absent_entire_menu"})
    with pytest.raises(Exception, match="frozen"):
        svc.set_item(db, "merchant-ui", d, "milk", "not_sure")
    db.rollback()
    with pytest.raises(Exception, match="never deleted"):
        db.execute(text("DELETE FROM merchant.declaration WHERE declaration_id = :d"), {"d": d})
    db.rollback()


def test_present_in_some_dishes_is_a_warning_for_a_preference_constraint_but_still_excludes_a_safety_one(env):
    """Decision D3, now integrated: 'some dishes contain it' softens a PREFERENCE constraint (dislike pork) to a high warning, while the same
    declaration still excludes the restaurant for a SAFETY constraint (religion). Replaces the interim test that pinned 'always excludes'."""
    client, db = env
    cid, d = submitted_declaration(client, db, "柒壹喫堂", {"pork": "present_in_some_dishes"})
    client.post(f"/ops/declarations/{d}/publish", headers=H)
    ext = db.scalar(text("SELECT presence_extent FROM enrichment.restaurant_attribute_evidence WHERE restaurant_id = :r AND attribute_code = 'pork' AND declaration_id = :d"), {"r": rid(db, "柒壹喫堂"), "d": d})
    assert ext == "some"
    row, resp = engine(client, db, "柒壹喫堂", "pork", reason="dislike")
    assert row[:3] == ("CONFIRMED_PRESENT", "WARN", "high")                       # softened: eligible, with a warning
    assert resp["excluded_count"] == 0 or "柒壹喫堂" not in [e["name"] for e in (client.get(f"/sessions/{resp['session_id']}/recommendations?include_excluded=true").json()["excluded"] or [])]
    row, _ = engine(client, db, "柒壹喫堂", "pork", reason="religion")
    assert row[:2] == ("CONFIRMED_PRESENT", "EXCLUDE")                             # safety constraint: not softened
    row, _ = engine(client, db, "柒壹喫堂", "pork", reason="unspecified")           # no reason -> pork is a preference-type attribute by default
    assert row[:2] == ("CONFIRMED_PRESENT", "WARN")


# ------------------------------------------------------------------ withdrawing a published declaration
def test_withdrawing_retires_positive_claims_keeps_risk_claims_and_lets_the_merchant_start_over(env):
    client, db = env
    cid, d = submitted_declaration(client, db, "港園牛肉麵", {"egg": ("absent_entire_menu", "confirmed_none"), "seafood": "present_in_most_dishes"})
    assert client.post(f"/ops/declarations/{d}/publish", headers=H).status_code == 200
    assert state(db, "港園牛肉麵", "egg") == "CONFIRMED_ABSENT" and state(db, "港園牛肉麵", "seafood") == "CONFIRMED_PRESENT"
    assert client.post(f"/ops/declarations/{d}/withdraw", json={"note": "短"}, headers=H).status_code == 422               # a reason is required
    assert client.post(f"/ops/declarations/{d}/withdraw", json={"note": "老闆來電說菜單改了"}, headers=H2).json()["positive_claims_retired"] == 1
    assert state(db, "港園牛肉麵", "egg") == "UNKNOWN"                                                                      # "no egg" stopped counting at once
    assert state(db, "港園牛肉麵", "seafood") == "CONFIRMED_PRESENT"                                                        # the risk claim stays: removing it would make users less careful
    detail = client.get(f"/ops/declarations/{d}", headers=H).json()
    assert detail["declaration"]["status"] == "withdrawn"
    event = [a for a in detail["audit"] if a["event"] == "withdrawn"][0]
    assert event["actor"] == "reviewer-b" and event["detail"]["positive_claims_retired"] == 1 and event["detail"]["risk_claims_kept_until_expiry"] == 1
    assert client.post(f"/ops/declarations/{d}/withdraw", json={"note": "再撤一次試試看"}, headers=H).status_code == 409   # only an approved declaration can be withdrawn
    assert svc.start_declaration(db, "merchant-ui", cid) != d                                                               # the merchant can declare again


def test_only_a_published_declaration_can_be_withdrawn(env):
    client, db = env
    cid, d = submitted_declaration(client, db, "蟳市長", {"soy": "absent_entire_menu"})
    r = client.post(f"/ops/declarations/{d}/withdraw", json={"note": "還沒發布就撤下"}, headers=H)
    assert r.status_code == 409 and "approved" in r.json()["message"]


# ------------------------------------------------------------------ kill switch through the API
def test_incident_suspends_positive_claims_and_resolution_restores_or_revokes(env):
    client, db = env
    cid, d = submitted_declaration(client, db, "東京小城", {"tree_nut": ("absent_entire_menu", "confirmed_none"), "seafood": "present_in_some_dishes"})
    client.post(f"/ops/declarations/{d}/publish", headers=H)
    assert state(db, "東京小城", "tree_nut") == "CONFIRMED_ABSENT"
    inc = client.post("/ops/incidents", json={"restaurant_id": str(rid(db, "東京小城")), "severity": "allergic_reaction", "description": "顧客通報過敏反應"}, headers=H)
    assert inc.status_code == 201 and inc.json()["suspended_evidence_count"] == 1
    assert state(db, "東京小城", "tree_nut") == "UNKNOWN" and state(db, "東京小城", "seafood") == "CONFIRMED_PRESENT"       # only the positive claim is suspended
    row, _ = engine(client, db, "東京小城", "tree_nut")
    assert row[:3] == ("UNKNOWN", "WARN", "critical")
    assert len(client.get("/ops/incidents", params={"status": "open"}, headers=H).json()["incidents"]) >= 1
    iid = inc.json()["incident_id"]
    assert client.post(f"/ops/incidents/{iid}/resolve", json={"outcome": "dismissed"}, headers=H).json()["status"] == "dismissed"
    assert state(db, "東京小城", "tree_nut") == "CONFIRMED_ABSENT"
    assert client.post(f"/ops/incidents/{iid}/resolve", json={"outcome": "dismissed"}, headers=H).status_code == 409
    inc2 = client.post("/ops/incidents", json={"restaurant_id": str(rid(db, "東京小城")), "severity": "allergic_reaction"}, headers=H).json()
    client.post(f"/ops/incidents/{inc2['incident_id']}/resolve", json={"outcome": "confirmed"}, headers=H)
    assert state(db, "東京小城", "tree_nut") == "UNKNOWN"
    assert db.scalar(text("SELECT count(*) FROM merchant.claim WHERE restaurant_id = :r AND status = 'verified'"), {"r": rid(db, "東京小城")}) == 0


# ------------------------------------------------------------------ decision D3: safety vs preference is a property of the CONSTRAINT
@pytest.mark.parametrize("reason,attribute,expected", [
    ("allergy", "beef", "safety"), ("medical", "seafood", "safety"), ("religion", "pork", "safety"),
    ("dislike", "peanut", "preference"), ("belief_diet", "vegetarian", "preference"),
    ("unspecified", "peanut", "safety"), ("unspecified", "gluten_free", "safety"), ("unspecified", "beef", "preference"), (None, "offal", "preference")])
def test_constraint_class_comes_from_the_reason_then_the_attribute_default(env, reason, attribute, expected):
    _, db = env
    assert db.scalar(text("SELECT ref.effective_constraint_class(:r, :a)"), {"r": reason, "a": attribute}) == expected


def test_ops_summary_and_dash_session_protection(env):
    """驗證 /ops/summary 統計端點與 Python Dash (/ops/dash/) 的 Cookie 存取保護流程。"""
    client, _db = env
    # 未帶驗證標頭呼叫 summary 與未帶 Cookie 存取 Dash 一律回傳 401
    assert client.get("/ops/summary").status_code == 401
    assert client.get("/ops/dash/").status_code == 401

    # 帶管理員標頭呼叫 summary 應回傳統計計數
    summary = client.get("/ops/summary", headers=H)
    assert summary.status_code == 200
    body = summary.json()
    assert body["user"] == "rev-1"
    for key in ("pending_declarations", "open_reports", "open_incidents", "active_claims", "total_restaurants", "total_sessions"):
        assert isinstance(body["counts"][key], int)

    # 簽發 Dash Cookie 後應能正常存取 /ops/dash/ 與 Dash 版面設定
    sess = client.post("/ops/dash-session", headers=H)
    assert sess.status_code == 200 and sess.json()["ok"] is True
    dash_html = client.get("/ops/dash/")
    assert dash_html.status_code == 200 and "揪呷 JOEAT" in dash_html.text
    dash_layout = client.get("/ops/dash/_dash-layout")
    assert dash_layout.status_code == 200

    # 登出清除 Cookie 後再次存取應被擋下
    logout = client.post("/ops/dash-logout")
    assert logout.status_code == 200
    assert client.get("/ops/dash/").status_code == 401
