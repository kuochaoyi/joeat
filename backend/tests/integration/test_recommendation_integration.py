"""Recommendation integration (decision record 0001, step 5): declarations in the results, strict allergy mode, report-a-mistake.

Runs on the scratch database from conftest (`merchant_env`), through the real API and the real engine.
"""
import uuid

import pytest
from sqlalchemy import text

from app.core.merchant_form import FORBIDDEN_WORDS
from app.services import reports
from tests.integration._merchant_helpers import H, rid, state, submitted_declaration

pytestmark = pytest.mark.integration


@pytest.fixture()
def env(merchant_env, client, db):
    return client, db


def declare(client, db, name, answers, **kw):
    cid, d = submitted_declaration(client, db, name, answers, **kw)
    r = client.post(f"/ops/declarations/{d}/publish", headers=H)
    assert r.status_code == 200, r.text
    return d


def session_with(client, items, strict=False, uid=None):
    sid = client.post("/sessions", json={"title": "t", "party_size": 2, "location_preset": "yancheng_pu"}).json()["session_id"]
    pid = client.post(f"/sessions/{sid}/participants", json={"line_user_id": uid or "i-" + uuid.uuid4().hex}).json()["participant_id"]
    client.post(f"/participants/{pid}/constraints", json={"items": items, "strict_allergy": strict})
    client.post(f"/participants/{pid}/preferences", json={"items": [{"cuisine_tag": "台式", "stance": "love"}]})
    resp = client.post(f"/sessions/{sid}/recommendations?include_excluded=true", json={"allow_partial": True})
    assert resp.status_code == 201, resp.text
    return sid, pid, resp.json()


def explanation(db, run_id, name):
    return db.scalar(text("SELECT c.explanation FROM product.recommendation_candidate c JOIN identity.restaurant r USING (restaurant_id) "
                          "WHERE c.run_id = :run AND r.canonical_name = :n"), {"run": run_id, "n": name})


PEANUT_ALLERGY = [{"attribute_code": "peanut", "reason": "allergy"}]


# ------------------------------------------------------------------ declarations in the results (D2)
def test_a_published_declaration_reaches_the_results_as_a_dated_statement_not_a_safety_claim(env):
    client, db = env
    declare(client, db, "鴨肉珍", {"peanut": ("absent_entire_menu", "confirmed_none")})
    today = db.scalar(text("SELECT to_char(ref.today_tpe(), 'YYYY/MM/DD')"))
    _, _, resp = session_with(client, PEANUT_ALLERGY)
    ex = explanation(db, resp["run_id"], "鴨肉珍")
    [d] = ex["declarations"]
    assert d["attribute"] == "peanut" and d["verified"] is True
    assert d["text"].startswith(f"店家於 {today} 聲明其目前菜單未使用花生；共用設備資訊：確認沒有共用")
    assert ex["hard_constraint"]["confirmed_safe"] == ["花生"]                              # API field kept; the UI shows the statement instead
    everything = str(ex).replace("不代表安全", "")                                               # the disclaimer denies safety; it must not be the only place the word appears
    assert not any(w in everything for w in FORBIDDEN_WORDS), "no stored explanation may promise safety"
    # the API exposes the same statement for a top-3 card
    for t in resp["top3"]:
        if t["name"] == "鴨肉珍":
            assert t["declarations"][0]["text"] == d["text"]


def test_the_statement_says_when_the_merchant_declared_not_when_a_reviewer_published_it(env):
    client, db = env
    cid, d = submitted_declaration(client, db, "阿英排骨飯", {"sesame": ("absent_entire_menu", "confirmed_none")})
    db.execute(text("UPDATE merchant.declaration SET attested_at = attested_at - interval '3 days' WHERE declaration_id = :d"), {"d": d})
    db.commit()
    assert client.post(f"/ops/declarations/{d}/publish", headers=H).status_code == 200                # published today, declared 3 days ago
    declared_day, today = db.execute(text("SELECT to_char(((attested_at AT TIME ZONE 'UTC') + interval '8 hours')::date, 'YYYY/MM/DD'), to_char(ref.today_tpe(), 'YYYY/MM/DD') FROM merchant.declaration WHERE declaration_id = :d"), {"d": d}).one()
    assert declared_day != today
    _, _, resp = session_with(client, [{"attribute_code": "sesame", "reason": "allergy"}])
    [stmt] = explanation(db, resp["run_id"], "阿英排骨飯")["declarations"]
    assert stmt["text"].startswith(f"店家於 {declared_day} 聲明") and today not in stmt["text"]
    # the stored evidence text carries the same date, and the reviewer's name stays in the audit trail only (the restaurant detail endpoint is public)
    detail = client.get(f"/restaurants/{rid(db, '阿英排骨飯')}").json()
    ev = [a for a in detail["attributes"] if a["attribute"] == "sesame"][0]["evidence_text"]
    assert "reviewer-a" not in ev and "聲明日" in ev and declared_day.replace("/", "-") in ev
    assert "reviewer-a" in str(client.get(f"/ops/declarations/{d}", headers=H).json()["audit"])


def test_possible_shared_equipment_and_unknown_shared_equipment_are_shown_differently(env):
    client, db = env
    declare(client, db, "柒壹喫堂", {"peanut": ("absent_entire_menu", "possible")})
    declare(client, db, "東京小城", {"peanut": ("absent_entire_menu", "unknown")})
    _, _, resp = session_with(client, PEANUT_ALLERGY)
    possible = explanation(db, resp["run_id"], "柒壹喫堂")
    unknown = explanation(db, resp["run_id"], "東京小城")
    wp, wu = possible["attribute_warnings"][0], unknown["attribute_warnings"][0]
    assert wp["code"] == "attribute_cross_contact_possible" and "共用設備可能有交叉接觸" in wp["text"]
    assert wu["code"] == "attribute_declared_shared_unknown" and "共用設備資訊：未知" in wu["text"]
    assert wp["level"] == wu["level"] == "critical"                                          # neither is downgraded by the declaration
    assert possible["hard_constraint"]["confirmed_safe"] == [] and possible["hard_constraint"]["unknown_attributes"] == []   # not "no data": it has its own wording
    assert possible["declarations"][0]["verified"] is False


def test_a_member_who_dislikes_pork_gets_a_warning_not_an_exclusion_when_only_some_dishes_have_it(env):
    client, db = env
    declare(client, db, "蟳市長", {"pork": "present_in_some_dishes"})
    _, _, resp = session_with(client, [{"attribute_code": "pork", "reason": "dislike"}])
    ex = explanation(db, resp["run_id"], "蟳市長")
    assert ex["hard_constraint"]["status"] == "partial_conflict"
    w = [x for x in ex["attribute_warnings"] if x["attribute"] == "pork"][0]
    assert w["code"] == "attribute_present_some" and w["level"] == "high"
    assert "蟳市長" not in [e["name"] for e in resp["excluded"]]
    # same declaration, but the member holds pork as a religious rule: excluded
    _, _, resp = session_with(client, [{"attribute_code": "pork", "reason": "religion"}])
    assert "蟳市長" in [e["name"] for e in resp["excluded"]]


# ------------------------------------------------------------------ strict allergy mode
def test_strict_allergy_mode_only_passes_restaurants_with_a_confirmed_absence(env):
    client, db = env
    declare(client, db, "鴨肉珍", {"peanut": ("absent_entire_menu", "confirmed_none")})        # CONFIRMED_ABSENT
    declare(client, db, "柒壹喫堂", {"peanut": ("absent_entire_menu", "possible")})            # LIKELY_ABSENT
    _, _, loose = session_with(client, PEANUT_ALLERGY)
    assert loose["strict_mode"] is False
    assert "柒壹喫堂" not in [e["name"] for e in loose["excluded"]]                            # normal mode: a critical warning, not an exclusion
    _, _, strict = session_with(client, PEANUT_ALLERGY, strict=True)
    assert strict["strict_mode"] is True
    names = [e["name"] for e in strict["excluded"]]
    assert "柒壹喫堂" in names and "東京小城" in names                                           # declared-but-unconfirmed and no data both excluded
    reasons = {e["name"]: e["reasons"] for e in strict["excluded"]}
    assert "花生：沒有店家確認" in reasons["柒壹喫堂"]
    assert strict["eligible_count"] == 1 and strict["top3"][0]["name"] == "鴨肉珍"
    assert strict["top3"][0]["warnings"] == [w for w in strict["top3"][0]["warnings"] if w.get("attribute") != "peanut"]   # nothing left to warn about for peanut


def test_strict_mode_leaves_everyone_elses_constraints_alone_and_reports_an_empty_result_honestly(env):
    client, db = env
    # a group of two: A strict about peanut, B has only a dislike. Nothing in this fresh database is confirmed-absent for peanut except what we publish.
    sid = client.post("/sessions", json={"title": "t", "party_size": 2, "location_preset": "yancheng_pu"}).json()["session_id"]
    a = client.post(f"/sessions/{sid}/participants", json={"line_user_id": "g-a-" + uuid.uuid4().hex}).json()["participant_id"]
    b = client.post(f"/sessions/{sid}/participants", json={"line_user_id": "g-b-" + uuid.uuid4().hex}).json()["participant_id"]
    client.post(f"/participants/{a}/constraints", json={"items": [{"attribute_code": "egg", "reason": "allergy"}], "strict_allergy": True})
    client.post(f"/participants/{b}/constraints", json={"items": [{"attribute_code": "beef", "reason": "dislike"}]})
    for p in (a, b):
        client.post(f"/participants/{p}/preferences", json={"items": []})
    resp = client.post(f"/sessions/{sid}/recommendations", json={"allow_partial": True}).json()
    assert resp["strict_mode"] is True and resp["eligible_count"] == 0 and resp["top3"] == []      # nobody confirmed egg: say so, do not invent a pick
    # without strict mode the same group still gets recommendations (with warnings)
    client.post(f"/participants/{a}/constraints", json={"items": [{"attribute_code": "egg", "reason": "allergy"}], "strict_allergy": False})
    resp = client.post(f"/sessions/{sid}/recommendations", json={"allow_partial": True}).json()
    assert resp["strict_mode"] is False and resp["eligible_count"] > 0


def test_strict_flag_is_reset_when_constraints_are_resubmitted_without_it(env):
    client, db = env
    sid, pid, _ = session_with(client, PEANUT_ALLERGY, strict=True)
    assert db.scalar(text("SELECT strict_allergy FROM product.participant WHERE participant_id = :p"), {"p": pid}) is True
    client.post(f"/participants/{pid}/constraints", json={"items": PEANUT_ALLERGY})
    assert db.scalar(text("SELECT strict_allergy FROM product.participant WHERE participant_id = :p"), {"p": pid}) is False


# ------------------------------------------------------------------ report a mistake
def report(client, restaurant, pid, **kw):
    body = {"participant_id": pid, "kind": "wrong_info", **kw}
    return client.post(f"/restaurants/{restaurant}/reports", json=body)


def test_a_report_is_queued_and_changes_nothing_until_a_reviewer_escalates(env):
    client, db = env
    declare(client, db, "鴨肉珍", {"peanut": ("absent_entire_menu", "confirmed_none")})
    _, pid, resp = session_with(client, PEANUT_ALLERGY)
    duck = rid(db, "鴨肉珍")
    r = report(client, duck, pid, attribute_code="peanut", note="我吃到花生醬")
    assert r.status_code == 201 and "不會改變推薦結果" in r.json()["message"]
    assert state(db, "鴨肉珍", "peanut") == "CONFIRMED_ABSENT"                                # still there: a report is not a verdict
    queue = client.get("/ops/reports?status=open", headers=H).json()["reports"]
    row = [x for x in queue if x["restaurant"] == "鴨肉珍"][0]
    assert row["note"] == "我吃到花生醬" and row["reporters_for_restaurant"] == 1
    assert "participant_id" not in row and str(pid) not in str(queue)                          # the reporter is never exposed to reviewers
    # escalate -> incident -> the positive claim is suspended
    e = client.post(f"/ops/reports/{row['report_id']}/escalate", json={"note": "查證後升級為事故"}, headers=H)
    assert e.status_code == 200 and e.json()["status"] == "escalated" and e.json()["incident_id"]
    assert state(db, "鴨肉珍", "peanut") != "CONFIRMED_ABSENT"
    assert client.post(f"/ops/reports/{row['report_id']}/escalate", json={"note": "再來一次試試"}, headers=H).status_code == 409


def test_a_wrong_info_report_the_reviewer_dismisses_leaves_the_claim_active(env):
    client, db = env
    declare(client, db, "東京小城", {"tree_nut": ("absent_entire_menu", "confirmed_none")})
    _, pid, _ = session_with(client, [{"attribute_code": "tree_nut", "reason": "allergy"}])
    rep = report(client, rid(db, "東京小城"), pid, kind="other", note="營業時間好像不對").json()["report_id"]
    d = client.post(f"/ops/reports/{rep}/dismiss", json={"note": "查證後資料正確"}, headers=H)
    assert d.status_code == 200 and d.json()["status"] == "dismissed" and d.json()["handled_by"] == "reviewer-a"
    assert state(db, "東京小城", "tree_nut") == "CONFIRMED_ABSENT"
    assert client.post(f"/ops/reports/{rep}/dismiss", json={"note": "重複處理看看"}, headers=H).status_code == 409
    assert client.post(f"/ops/reports/{rep}/dismiss", json={"note": "短"}, headers=H).status_code == 422          # a note is required
    assert client.get("/ops/reports").status_code == 401                                                           # reviewers only


def test_report_limits_per_person_and_per_restaurant_and_only_for_restaurants_you_saw(env, monkeypatch):
    client, db = env
    _, pid, resp = session_with(client, PEANUT_ALLERGY)
    names = ["鴨肉珍", "東京小城", "柒壹喫堂", "蟳市長"]
    assert report(client, rid(db, names[0]), pid, attribute_code="peanut").status_code == 201
    dup = report(client, rid(db, names[0]), pid, attribute_code="peanut")
    assert dup.status_code == 429 and dup.json()["error"] == "already_reported"                # same restaurant + attribute twice
    assert report(client, rid(db, names[0]), pid, attribute_code="beef").status_code == 201    # a different attribute is a different report
    assert report(client, rid(db, names[1]), pid).status_code == 201
    over = report(client, rid(db, names[2]), pid)
    assert over.status_code == 429 and over.json()["error"] == "rate_limited"                  # the 4th report in 24 hours
    # a restaurant that was never a candidate in this session cannot be reported
    outside = db.scalar(text("SELECT restaurant_id FROM identity.restaurant WHERE pool_status <> 'in_pool' LIMIT 1"))
    _, pid2, _ = session_with(client, PEANUT_ALLERGY)
    nope = report(client, outside, pid2)
    assert nope.status_code == 403 and nope.json()["error"] == "not_a_candidate"
    assert report(client, uuid.uuid4(), pid2).status_code == 404                               # unknown restaurant
    assert report(client, rid(db, names[0]), str(uuid.uuid4())).status_code == 404                  # unknown participant
    assert client.post(f"/restaurants/{rid(db, names[3])}/reports", json={"participant_id": str(pid2), "kind": "bogus"}).status_code == 422
    # the open queue of one restaurant is capped so a flood never reaches a reviewer
    monkeypatch.setattr(reports, "OPEN_PER_RESTAURANT", 1)
    full = report(client, rid(db, names[0]), pid2, attribute_code="gluten")
    assert full.status_code == 429 and full.json()["error"] == "queue_full"
