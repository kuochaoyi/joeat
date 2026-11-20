"""Merchant-facing API (/merchant/*, entered with the invitation token) and demo-data isolation. Runs on the scratch database from conftest (`merchant_env`)."""
import json
import uuid

import pytest
from sqlalchemy import text

from app.core import merchant_form as form
from app.services import merchant as svc
from tests.integration._merchant_helpers import CALL_NOTE, H, engine, rid, state, verified_claim

pytestmark = pytest.mark.integration


@pytest.fixture()
def env(merchant_env, client, db):
    return client, db


def invite(client, db, name, *, verify=True, method="phone_callback", is_demo=False, role="owner"):
    r = client.post("/ops/claims", json={"restaurant_id": str(rid(db, name)), "is_demo": is_demo}, headers=H)
    assert r.status_code == 201, r.text
    token, cid = r.json()["token"], r.json()["claim_id"]
    if verify:
        v = client.post(f"/ops/claims/{cid}/verify", json={"method": method, "note": CALL_NOTE, "claimant_role": role}, headers=H)
        assert v.status_code == 200, v.text
    return token, cid


def T(token):
    return {"X-Claim-Token": token}


def fill(client, token, answers, menu=None):
    """answers: {attribute: answer | (answer, cross_contact_status, note, certificate)}"""
    items = []
    for attr, v in answers.items():
        v = v if isinstance(v, tuple) else (v,)
        items.append({"attribute_code": attr, "answer": v[0], "cross_contact_status": v[1] if len(v) > 1 else "unknown",
                      "note": v[2] if len(v) > 2 else None, "certificate_ref": v[3] if len(v) > 3 else None})
    assert client.put("/merchant/declaration/items", json={"items": items}, headers=T(token)).status_code == 200
    if menu:
        assert client.put("/merchant/declaration/menu", json={"menu_url": menu}, headers=T(token)).status_code == 200


def submit(client, token, db, role="owner", accepted=True, version=form.ATTESTATION_VERSION):
    return client.post("/merchant/declaration/submit", json={"role": role, "menu_as_of": str(db.scalar(text("SELECT ref.today_tpe()"))), "accepted": accepted, "attestation_version": version},
                       headers=T(token))


# ------------------------------------------------------------------ the form specification
def test_form_spec_covers_exactly_the_attributes_the_engine_knows_and_defaults_to_not_sure(env):
    client, db = env
    spec = client.get("/merchant/form-spec").json()
    codes = [i["attribute_code"] for sec in spec["sections"] for i in sec["items"]]
    assert sorted(codes) == sorted(r[0] for r in db.execute(text("SELECT attribute_code FROM ref.attribute WHERE is_active")))
    assert [s["key"] for s in spec["sections"]] == ["allergens", "ingredients", "diets", "needs"]       # the safety-critical questions come first; the group-need questions (pet / child) last
    assert spec["default_answer"] == "not_sure"
    for sec in spec["sections"]:
        for it in sec["items"]:
            assert it["answers"][-1] == {"value": "not_sure", "label": "我不確定"}, "'not sure' is always offered, last"
            assert (it["cross_contact"] is not None) == (it["type"] == "avoid"), "shared equipment is asked for avoid-type items only"
            assert it["certificate"] == (it["attribute_code"] == "halal")
            assert {a["value"] for a in it["answers"]} <= ({"absent_entire_menu", "present_in_some_dishes", "present_in_most_dishes", "not_sure"} if it["type"] == "avoid" else {"offered", "not_offered", "not_sure"})
    assert spec["legal_review"]["status"] == "pending" and spec["attestation"]["version"] == form.ATTESTATION_VERSION


def test_nothing_the_merchant_reads_promises_safety(env):
    """Decision D2: the form, the attestation and every preview sentence state facts; they never use the forbidden words."""
    client, db = env
    blob = json.dumps(client.get("/merchant/form-spec").json(), ensure_ascii=False) + form.ATTESTATION_TEXT
    sample = {"attribute_type": "avoid", "cross_contact_status": "confirmed_none", "presence_extent": None, "capped_by_cross_contact": False, "attribute_code": "peanut"}
    from datetime import date
    for st in ("CONFIRMED_ABSENT", "LIKELY_ABSENT", "CONFIRMED_PRESENT", "LIKELY_PRESENT"):
        for capped in (False, True):
            for code, typ in (("peanut", "avoid"), ("halal", "require")):
                blob += form.describe({**sample, "new_state": st, "capped_by_cross_contact": capped, "attribute_code": code, "attribute_type": typ}, date(2026, 11, 4))["text"]
    blob += form.describe({**sample, "new_state": "CONFIRMED_ABSENT", "attribute_type": "require", "attribute_code": "vegan"}, date(2026, 11, 4))["text"]
    assert not [w for w in form.FORBIDDEN_WORDS if w in blob], [w for w in form.FORBIDDEN_WORDS if w in blob]


# ------------------------------------------------------------------ the token
def test_token_is_required_and_unknown_tokens_get_a_generic_answer(env):
    client, db = env
    assert client.get("/merchant/me").status_code == 401
    a = client.get("/merchant/me", headers=T("not-a-token"))
    b = client.get("/merchant/me", headers=T("another-wrong-one"))
    assert a.status_code == b.status_code == 404 and a.json() == b.json()
    assert client.get(f"/merchant/me?token=anything").status_code == 401, "the token is only accepted in the header, never in the URL"


def test_revoked_and_expired_invitations_are_gone(env):
    client, db = env
    token, cid = invite(client, db, "鴨肉珍")
    assert client.get("/merchant/me", headers=T(token)).status_code == 200
    client.post(f"/ops/claims/{cid}/revoke", headers=H)
    r = client.get("/merchant/me", headers=T(token))
    assert r.status_code == 410 and r.json()["error"] == "claim_unavailable"
    token2, cid2 = invite(client, db, "鴨肉珍")
    db.execute(text("UPDATE merchant.claim SET expires_at = now() - interval '1 day' WHERE claim_id = :c"), {"c": cid2})
    db.commit()
    assert client.get("/merchant/me", headers=T(token2)).status_code == 410


def test_an_unverified_merchant_can_look_but_not_declare(env):
    client, db = env
    token, _ = invite(client, db, "老蔡虱目魚粥", verify=False)
    me = client.get("/merchant/me", headers=T(token)).json()
    assert me["can_declare"] is False and me["claim_status"] == "invited" and "聯絡確認身分" in me["message"] and me["restaurant"]["name"] == "老蔡虱目魚粥"
    r = client.post("/merchant/declaration", headers=T(token))
    assert r.status_code == 409 and r.json()["error"] == "not_verified"


def test_the_merchant_only_ever_sees_its_own_restaurant_and_no_internals(env):
    client, db = env
    t1, _ = invite(client, db, "鴨肉珍")
    t2, _ = invite(client, db, "阿英排骨飯")
    me1, me2 = client.get("/merchant/me", headers=T(t1)), client.get("/merchant/me", headers=T(t2))
    assert me1.json()["restaurant"]["name"] == "鴨肉珍" and me2.json()["restaurant"]["name"] == "阿英排骨飯"
    for resp in (me1, me2, client.post("/merchant/declaration", headers=T(t1))):
        body = resp.text
        assert t1 not in body and t2 not in body and "token_hash" not in body and "verified_by" not in body and "reviewer" not in body
    d1 = client.get("/merchant/declaration", headers=T(t1)).json()["declaration_id"]
    d2 = client.post("/merchant/declaration", headers=T(t2)).json()["declaration_id"]
    assert d1 != d2


# ------------------------------------------------------------------ the whole path, merchant side -> reviewer -> evidence -> recommendation
def test_full_path_from_the_merchant_form_to_a_confirmed_claim_in_the_recommendation(env):
    client, db = env
    token, cid = invite(client, db, "鴨肉珍")
    d = client.post("/merchant/declaration", headers=T(token))
    assert d.status_code == 201 and d.json()["status"] == "draft" and len(d.json()["items"]) == 19
    assert {i["answer"] for i in d.json()["items"]} == {"not_sure"} and {i["cross_contact_status"] for i in d.json()["items"]} == {"unknown"}
    assert client.post("/merchant/declaration", headers=T(token)).json()["declaration_id"] == d.json()["declaration_id"], "starting twice returns the open draft"

    fill(client, token, {"peanut": ("absent_entire_menu", "confirmed_none", "炒鍋每日清洗"), "pork": "present_in_most_dishes", "halal": ("offered", "unknown", None, "HALAL-0001")},
         menu="https://example.invalid/menu.pdf")
    saved = client.get("/merchant/declaration", headers=T(token)).json()
    assert {i["attribute_code"]: i["answer"] for i in saved["items"] if i["answer"] != "not_sure"} == {"peanut": "absent_entire_menu", "pork": "present_in_most_dishes", "halal": "offered"}
    assert saved["menu_url"] == "https://example.invalid/menu.pdf"

    pv = client.get("/merchant/declaration/preview", headers=T(token)).json()
    lines = {x["attribute_code"]: x for x in pv["lines"]}
    today = db.scalar(text("SELECT ref.today_tpe()"))
    assert lines["peanut"]["text"] == f"店家於 {today} 聲明其目前菜單未使用花生；共用設備：確認無共用。" and lines["peanut"]["effect"] == "confirmed"
    assert lines["pork"]["text"] == "店家聲明大部分餐點含有豬肉。" and lines["pork"]["effect"] == "contains"
    assert lines["halal"]["effect"] == "confirmed" and pv["counts"] == {"confirmed": 2, "possible": 0, "contains": 1}
    assert "資訊不足" in pv["unanswered_note"]
    assert state(db, "鴨肉珍", "peanut") == "UNKNOWN", "nothing is evidence before a reviewer publishes it"

    assert submit(client, token, db, accepted=False).status_code == 422
    assert submit(client, token, db, version="attest-v-old").status_code == 409
    ok = submit(client, token, db)
    assert ok.status_code == 200 and ok.json()["status"] == "submitted" and ok.json()["editable"] is False and ok.json()["declared_role"] == "owner"
    assert client.put("/merchant/declaration/items", json={"items": [{"attribute_code": "peanut", "answer": "not_sure"}]}, headers=T(token)).status_code == 409
    assert submit(client, token, db).status_code == 409

    queue = client.get("/ops/declarations", params={"status": "submitted"}, headers=H).json()["declarations"]
    did = next(x["declaration_id"] for x in queue if x["restaurant"] == "鴨肉珍")
    assert client.post(f"/ops/declarations/{did}/publish", headers=H).status_code == 200
    row, resp = engine(client, db, "鴨肉珍", "peanut")
    assert row == ("CONFIRMED_ABSENT", "PASS", "none", True, "official_menu"), "a real (non-demo) claim is visible to the engine with no flag"
    assert resp["test_evidence_enabled"] is False
    assert state(db, "鴨肉珍", "halal") == "CONFIRMED_PRESENT" and state(db, "鴨肉珍", "pork") == "CONFIRMED_PRESENT"


def test_preview_tells_the_merchant_when_an_answer_will_not_count_as_confirmed(env):
    client, db = env
    token, _ = invite(client, db, "田記豆漿", method="official_channel_message")                         # basic verification
    client.post("/merchant/declaration", headers=T(token))
    fill(client, token, {"egg": ("absent_entire_menu", "confirmed_none")})
    line = client.get("/merchant/declaration/preview", headers=T(token)).json()["lines"][0]
    assert line["effect"] == "possible" and "未確認含有蛋" in line["text"] and "尚未完成進一步驗證" in line["text"]
    token2, _ = invite(client, db, "小韓國")
    client.post("/merchant/declaration", headers=T(token2))
    fill(client, token2, {"sesame": ("absent_entire_menu", "possible"), "soy": ("absent_entire_menu", "confirmed_shared")})
    lines = {x["attribute_code"]: x for x in client.get("/merchant/declaration/preview", headers=T(token2)).json()["lines"]}
    assert lines["sesame"]["effect"] == "possible" and "共用設備尚未確認無共用" in lines["sesame"]["text"]
    assert lines["soy"]["effect"] == "contains" and "共用設備" in lines["soy"]["text"] and "視為可能含有大豆" in lines["soy"]["text"]


def test_bad_input_is_rejected(env):
    client, db = env
    token, _ = invite(client, db, "大智羊肉")
    client.post("/merchant/declaration", headers=T(token))
    put = lambda items: client.put("/merchant/declaration/items", json={"items": items}, headers=T(token))   # noqa: E731
    assert put([{"attribute_code": "peanut", "answer": "offered"}]).status_code == 409                          # not valid for an avoid-type attribute (database rule)
    assert put([{"attribute_code": "vegan", "answer": "absent_entire_menu"}]).status_code == 409
    assert put([{"attribute_code": "unobtainium", "answer": "not_sure"}]).status_code == 422
    assert put([{"attribute_code": "peanut", "answer": "definitely"}]).status_code == 422
    assert client.put("/merchant/declaration/menu", json={"menu_url": "javascript:alert(1)"}, headers=T(token)).status_code == 422
    r = client.post("/merchant/declaration/submit", json={"role": "owner", "menu_as_of": "2999-01-01", "accepted": True, "attestation_version": form.ATTESTATION_VERSION}, headers=T(token))
    assert r.status_code == 409 and "menu_as_of" in r.json()["message"]
    assert client.post("/merchant/declaration/submit", json={"role": "janitor", "menu_as_of": "2026-01-01", "accepted": True, "attestation_version": form.ATTESTATION_VERSION}, headers=T(token)).status_code == 422


def test_sent_back_for_information_the_merchant_can_edit_and_resubmit(env):
    client, db = env
    token, cid = invite(client, db, "九記 鹽埕食糖水")
    client.post("/merchant/declaration", headers=T(token))
    fill(client, token, {"gluten": "absent_entire_menu"})
    assert submit(client, token, db).status_code == 200
    did = client.get("/merchant/declaration", headers=T(token)).json()["declaration_id"]
    client.post(f"/ops/declarations/{did}/needs-info", json={"note": "請附上最新菜單連結"}, headers=H)
    me = client.get("/merchant/me", headers=T(token)).json()["declaration"]
    assert me["status"] == "needs_info" and me["review_note"] == "請附上最新菜單連結" and me["editable"] is True
    fill(client, token, {"gluten": ("absent_entire_menu", "confirmed_none")}, menu="https://example.invalid/m.pdf")
    assert submit(client, token, db).json()["status"] == "submitted"


# ------------------------------------------------------------------ demo isolation: fake declarations never become real evidence
def test_demo_claims_are_refused_unless_test_evidence_is_enabled(env, monkeypatch):
    from app.core.config import get_settings
    client, db = env
    monkeypatch.setenv("ALLOW_TEST_EVIDENCE", "false")
    get_settings.cache_clear()
    r = client.post("/ops/claims", json={"restaurant_id": str(rid(db, "鴨肉珍")), "is_demo": True}, headers=H)
    assert r.status_code == 409 and r.json()["error"] == "demo_disabled"
    get_settings.cache_clear()


def test_demo_declarations_are_invisible_to_the_engine_unless_the_flag_is_on_and_the_ui_is_told(env, monkeypatch):
    from app.core.config import get_settings
    client, db = env
    monkeypatch.setenv("ALLOW_TEST_EVIDENCE", "true")
    get_settings.cache_clear()
    try:
        token, cid = invite(client, db, "大溝頂虱目魚米粉湯", is_demo=True)
        assert client.get("/merchant/me", headers=T(token)).json()["demo"] is True
        client.post("/merchant/declaration", headers=T(token))
        fill(client, token, {"milk": ("absent_entire_menu", "confirmed_none")}, menu="https://example.invalid/demo.pdf")
        assert submit(client, token, db).status_code == 200
        did = client.get("/merchant/declaration", headers=T(token)).json()["declaration_id"]
        assert client.post(f"/ops/declarations/{did}/publish", headers=H).status_code == 200
        src = db.scalar(text("SELECT s.source_type FROM enrichment.restaurant_attribute_evidence e JOIN ref.data_source s USING (source_id) WHERE e.declaration_id = :d AND e.attribute_code = 'milk'"), {"d": did})
        assert src == "test_fixture", "demo claims publish into the TEST source, never the real first-party source"

        row, resp = engine(client, db, "大溝頂虱目魚米粉湯", "milk")                        # flag ON: the engine sees it, and says so
        assert row[:2] == ("CONFIRMED_ABSENT", "PASS") and resp["test_evidence_enabled"] is True

        monkeypatch.setenv("ALLOW_TEST_EVIDENCE", "false")
        get_settings.cache_clear()
        row, resp = engine(client, db, "大溝頂虱目魚米粉湯", "milk")                        # flag OFF: as if it never happened
        assert row[:3] == ("UNKNOWN", "WARN", "critical") and resp["test_evidence_enabled"] is False
        assert db.scalar(text("SELECT count(*) FROM enrichment.restaurant_attribute_evidence e JOIN ref.data_source s USING (source_id) WHERE s.source_type = 'first_party' AND e.attribute_code = 'milk' AND e.restaurant_id = :r"),
                         {"r": rid(db, "大溝頂虱目魚米粉湯")}) == 0, "no real first-party row was ever written"
    finally:
        get_settings.cache_clear()


def test_a_demo_declaration_does_not_touch_real_first_party_evidence(env, monkeypatch):
    from app.core.config import get_settings
    client, db = env
    monkeypatch.setenv("ALLOW_TEST_EVIDENCE", "true")
    get_settings.cache_clear()
    try:
        # a REAL strong declaration for 大智羊肉 first
        from tests.integration._merchant_helpers import submitted_declaration
        _, real = submitted_declaration(client, db, "大智羊肉", {"tree_nut": ("absent_entire_menu", "confirmed_none")}, menu="https://example.invalid/real.pdf")
        client.post(f"/ops/declarations/{real}/publish", headers=H)
        assert state(db, "大智羊肉", "tree_nut") == "CONFIRMED_ABSENT"
        # then a DEMO declaration for the same restaurant that says something different
        token, _ = invite(client, db, "大智羊肉", is_demo=True)
        client.post("/merchant/declaration", headers=T(token))
        fill(client, token, {"sesame": ("absent_entire_menu", "confirmed_none")}, menu="https://example.invalid/demo.pdf")
        submit(client, token, db)
        did = client.get("/merchant/declaration", headers=T(token)).json()["declaration_id"]
        assert client.post(f"/ops/declarations/{did}/publish", headers=H).status_code == 200
        real_status = db.scalar(text("SELECT e.status FROM enrichment.restaurant_attribute_evidence e JOIN ref.data_source s USING (source_id) "
                                     "WHERE s.source_type = 'first_party' AND e.attribute_code = 'tree_nut' AND e.restaurant_id = :r"), {"r": rid(db, "大智羊肉")})
        assert real_status == "active", "the demo declaration must not retire real evidence (even though it did not re-assert tree_nut)"
    finally:
        get_settings.cache_clear()
