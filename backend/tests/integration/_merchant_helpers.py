"""Shared helpers for the merchant integration tests (reviewer API, merchant portal, demo isolation)."""
import uuid

from sqlalchemy import text

from app.services import merchant as svc

H = {"X-Ops-Key": "test-ops-key", "X-Ops-User": "reviewer-a"}
H2 = {"X-Ops-Key": "test-ops-key", "X-Ops-User": "reviewer-b"}
CALL_NOTE = "撥打公開電話，由老闆本人接聽並確認菜單"


def rid(db, name):
    return db.scalar(text("SELECT restaurant_id FROM identity.restaurant WHERE canonical_name = :n"), {"n": name})


def verified_claim(client, db, name, method="phone_callback", note=CALL_NOTE, role="owner"):
    claim = client.post("/ops/claims", json={"restaurant_id": str(rid(db, name))}, headers=H)
    assert claim.status_code == 201, claim.text
    cid = claim.json()["claim_id"]
    r = client.post(f"/ops/claims/{cid}/verify", json={"method": method, "note": note, "claimant_role": role}, headers=H)
    assert r.status_code == 200, r.text
    return cid


def submitted_declaration(client, db, name, answers, *, menu=None, **claim_kw):
    """answers: {attribute: answer | (answer, cross_contact_status)}"""
    cid = verified_claim(client, db, name, **claim_kw)
    d = svc.start_declaration(db, "merchant-ui", cid)
    for attr, v in answers.items():
        ans, cc = v if isinstance(v, tuple) else (v, "unknown")
        svc.set_item(db, "merchant-ui", d, attr, ans, cross_contact_status=cc, note=None)
    if menu:
        svc.set_menu(db, "merchant-ui", d, menu)
    svc.submit_declaration(db, "merchant-ui", d, "owner", db.scalar(text("SELECT ref.today_tpe()")), "attest-v1")
    return cid, d


def engine(client, db, name, attr, reason="allergy"):
    """One participant with one hard constraint -> real recommendation run -> the stored check row for that restaurant."""
    sid = client.post("/sessions", json={"title": "t", "party_size": 2, "location_preset": "yancheng_pu"}).json()["session_id"]
    pid = client.post(f"/sessions/{sid}/participants", json={"line_user_id": "m-" + uuid.uuid4().hex}).json()["participant_id"]
    client.post(f"/participants/{pid}/constraints", json={"items": [{"attribute_code": attr, "reason": reason}]})
    client.post(f"/participants/{pid}/preferences", json={"items": [{"cuisine_tag": "台式", "stance": "love"}, {"cuisine_tag": "小吃", "stance": "love"}]})
    resp = client.post(f"/sessions/{sid}/recommendations", json={"allow_partial": True}).json()
    row = db.execute(text(
        "SELECT evidence_state::text, action, warning_level, may_show_safe_badge, evidence_snapshot->>'basis' FROM product.recommendation_constraint_check k "
        "JOIN identity.restaurant r USING (restaurant_id) WHERE k.run_id = :run AND r.canonical_name = :n"), {"run": resp["run_id"], "n": name}).one()
    return tuple(row), resp


def state(db, name, attr):
    r = db.execute(text("SELECT state::text FROM enrichment.restaurant_attribute_state WHERE restaurant_id = :r AND attribute_code = :a"), {"r": rid(db, name), "a": attr}).first()
    return r[0] if r else "UNKNOWN"
