"""End-to-end API tests: 3 participants, the seeded Yancheng restaurants -> Top 3 with explanations."""
import uuid

import pytest
from sqlalchemy import func, select, text

from app.demo_scenario import run_demo
from app.models.identity import Restaurant
from app.models.product import (
    Participant, RecommendationCandidate, RecommendationConstraintCheck, RecommendationRun, RecommendationScoreComponent,
)

pytestmark = pytest.mark.integration


def test_demo_scenario_end_to_end(client, uniq):
    demo = run_demo(client, user_prefix=uniq)
    assert demo["progress"]["all_complete"] and demo["progress"]["joined"] == 3
    r = demo["result"]
    assert len(r["top3"]) == 3 and [t["rank"] for t in r["top3"]] == [1, 2, 3]

    excluded = {e["name"]: e["reasons"] for e in r["excluded"]}
    assert "港園牛肉麵" in excluded and any("牛肉" in x for x in excluded["港園牛肉麵"]), "beef CONFIRMED_PRESENT must exclude (A: no beef)"
    assert "郭家肉粽" in excluded and any("花生" in x for x in excluded["郭家肉粽"]), "peanut LIKELY_PRESENT on a critical allergen must exclude (B)"
    assert r["excluded_count"] == len(excluded) == 2 and r["pool_size"] == 15 and r["eligible_count"] == 13

    names = {t["name"]: t for t in r["top3"]}
    assert not set(names) & set(excluded)
    jp = [t for t in r["top3"] if "日式" in t["cuisines"]]
    hotpot = [t for t in r["top3"] if "火鍋" in t["cuisines"]]
    assert jp and hotpot, "the Japanese and hotpot restaurants must surface through their cuisine bonus"
    assert all(t["score"]["cuisine"] == 3 for t in jp + hotpot)           # exactly one participant loves it; C is neutral
    for t in r["top3"]:
        # peanut data is UNKNOWN for every Top 3 restaurant -> a critical warning, never a "safe" claim
        pw = [w for w in t["warnings"] if w.get("attribute") == "peanut"]
        assert pw and pw[0]["level"] == "critical" and "資訊不足" in pw[0]["text"]
        assert t["hard_constraint"]["confirmed_safe"] == [] and "花生" in t["hard_constraint"]["unknown_attributes"]
        assert t["score"]["rating"] is None and t["score"]["total"] == t["score"]["cuisine"] + t["score"]["distance"] + t["score"]["data_confidence"]
        assert t["reasons"] and t["summary"]


def test_everything_is_persisted_including_excluded_candidates(client, db, uniq):
    demo = run_demo(client, user_prefix=uniq)
    run_id = uuid.UUID(demo["result"]["run_id"])
    run = db.get(RecommendationRun, run_id)
    assert run.completed_at is not None and run.scoring_version == "v1" and run.config_snapshot["top_n"] == 3
    cands = db.scalars(select(RecommendationCandidate).where(RecommendationCandidate.run_id == run_id)).all()
    assert len(cands) == run.pool_size == 15
    assert sorted(c.stage for c in cands).count("excluded") == 2 and sorted(c.stage for c in cands).count("top3") == 3
    for c in cands:
        if c.stage == "excluded":
            assert c.total_score is None and c.rank is None
        else:
            comps = db.scalars(select(RecommendationScoreComponent).where(RecommendationScoreComponent.run_id == run_id, RecommendationScoreComponent.restaurant_id == c.restaurant_id)).all()
            assert float(c.total_score) == pytest.approx(sum(float(x.points) for x in comps))
            assert {x.component for x in comps} == {"cuisine_preference", "distance", "data_confidence", "rating", "price"}
    # every (restaurant x constraint) has an auditable check row, excluded restaurants included
    n_checks = db.scalar(select(func.count()).select_from(RecommendationConstraintCheck).where(RecommendationConstraintCheck.run_id == run_id))
    assert n_checks == 15 * 2                                              # 2 hard constraints (beef, peanut) x 15 restaurants
    ex = db.scalars(select(RecommendationConstraintCheck).where(RecommendationConstraintCheck.run_id == run_id, RecommendationConstraintCheck.action == "EXCLUDE")).all()
    assert {(x.attribute_code, x.evidence_state) for x in ex} == {("beef", "CONFIRMED_PRESENT"), ("peanut", "LIKELY_PRESENT")}
    assert all(x.deciding_evidence_id and x.evidence_snapshot and x.evidence_snapshot["basis"] for x in ex), "an exclusion must cite its evidence"


def test_get_recommendations_returns_the_stored_run(client, uniq):
    demo = run_demo(client, user_prefix=uniq)
    sid = demo["session"]["session_id"]
    again = client.get(f"/sessions/{sid}/recommendations")
    assert again.status_code == 200
    assert [t["restaurant_id"] for t in again.json()["top3"]] == [t["restaurant_id"] for t in demo["result"]["top3"]]
    assert again.json()["run_id"] == demo["result"]["run_id"]


def test_no_recommendation_before_a_run_and_incomplete_sessions_are_refused(client, uniq):
    s = client.post("/sessions", json={"title": "x", "party_size": 3}).json()
    sid = s["session_id"]
    assert client.get(f"/sessions/{sid}/recommendations").status_code == 404
    assert client.post(f"/sessions/{sid}/recommendations").status_code == 409            # nobody joined
    p = client.post(f"/sessions/{sid}/participants", json={"line_user_id": uniq + "-a"}).json()
    r = client.post(f"/sessions/{sid}/recommendations")
    assert r.status_code == 409 and r.json()["error"] == "incomplete"
    client.post(f"/participants/{p['participant_id']}/constraints", json={"items": []})
    client.post(f"/participants/{p['participant_id']}/preferences", json={"items": []})
    forced = client.post(f"/sessions/{sid}/recommendations", json={"allow_partial": True})
    assert forced.status_code == 201 and forced.json()["participants"] == 1


def test_validation_and_limits(client, uniq):
    assert client.post("/sessions", json={"title": "x", "party_size": 21}).status_code == 422
    assert client.post("/sessions", json={"title": "x", "party_size": 1}).status_code == 422
    assert client.post("/sessions", json={"title": "x", "party_size": 3, "location_preset": "nowhere"}).status_code == 422
    sid = client.post("/sessions", json={"title": "x", "party_size": 2}).json()["session_id"]
    a = client.post(f"/sessions/{sid}/participants", json={"line_user_id": uniq + "-a"})
    again = client.post(f"/sessions/{sid}/participants", json={"line_user_id": uniq + "-a"})
    assert a.json()["participant_id"] == again.json()["participant_id"], "joining twice must be idempotent"
    assert client.post(f"/sessions/{sid}/participants", json={"line_user_id": uniq + "-b"}).status_code == 201
    full = client.post(f"/sessions/{sid}/participants", json={"line_user_id": uniq + "-c"})
    assert full.status_code == 409 and full.json()["error"] == "session_full"
    pid = a.json()["participant_id"]
    assert client.post(f"/participants/{pid}/constraints", json={"items": [{"attribute_code": "unobtainium"}]}).status_code == 422
    assert client.post(f"/participants/{pid}/constraints", json={"items": [{"attribute_code": "beef", "reason": "bogus"}]}).status_code == 422
    assert client.post(f"/participants/{pid}/constraints", json={"items": [{"attribute_code": "beef"}, {"attribute_code": "beef"}]}).status_code == 422
    assert client.post(f"/participants/{pid}/preferences", json={"items": [{"cuisine_tag": "台式", "stance": "maybe"}]}).status_code == 422
    assert client.post(f"/participants/{pid}/preferences", json={"items": [{"cuisine_tag": "外星料理", "stance": "love"}]}).status_code == 422
    assert client.get(f"/sessions/{uuid.uuid4()}").status_code == 404


def test_resubmitting_replaces_instead_of_accumulating(client, db, uniq):
    sid = client.post("/sessions", json={"title": "x", "party_size": 2}).json()["session_id"]
    pid = client.post(f"/sessions/{sid}/participants", json={"line_user_id": uniq}).json()["participant_id"]
    client.post(f"/participants/{pid}/constraints", json={"items": [{"attribute_code": "beef"}, {"attribute_code": "pork"}]})
    r = client.post(f"/participants/{pid}/constraints", json={"items": [{"attribute_code": "pork"}]})
    assert r.json()["saved"] == 1
    n = db.scalar(text("SELECT count(*) FROM product.participant_hard_constraint WHERE participant_id = :p"), {"p": pid})
    assert n == 1


def test_privacy_nobody_sees_anybody_elses_constraints(client, db, uniq):
    demo = run_demo(client, user_prefix=uniq)
    sid = demo["session"]["session_id"]
    blobs = [client.get(f"/sessions/{sid}/progress").text, client.get(f"/sessions/{sid}/recommendations", params={"include_excluded": "true"}).text, str(demo["result"])]
    for blob in blobs:
        assert "allergy" not in blob and "participant_hard" not in blob
    prog = client.get(f"/sessions/{sid}/progress").json()
    assert set(prog["participants"][0]) == {"label", "is_me", "constraints_done", "preferences_done"}      # counts only: no contents, no participant ids (they are capabilities)
    assert not any(p["participant_id"] in client.get(f"/sessions/{sid}/progress").text for p in [{"participant_id": pid} for pid in demo["participants"].values()])
    mine = client.get(f"/sessions/{sid}/progress", params={"participant_id": demo["participants"]["B"]}).json()["participants"]
    assert [p["label"] for p in mine if p["is_me"]] == ["B"]
    # raw LINE identifiers are never stored, only hashes
    refs = db.scalars(select(Participant.line_user_ref).where(Participant.session_id == uuid.UUID(sid))).all()
    assert refs and all(len(x) == 64 and uniq not in x for x in refs)
    g = client.post("/sessions", json={"title": "g", "party_size": 2, "line_group_id": "Cgroup-raw-id"}).json()
    raw = db.scalar(text("SELECT line_group_ref FROM product.dining_session WHERE session_id = :s"), {"s": g["session_id"]})
    assert raw and raw != "Cgroup-raw-id" and len(raw) == 64


def test_budget_never_excludes_and_is_reported_as_unknown(client, db, uniq):
    sid = client.post("/sessions", json={"title": "budget", "party_size": 2, "location_preset": "yancheng_pu"}).json()["session_id"]
    pid = client.post(f"/sessions/{sid}/participants", json={"line_user_id": uniq}).json()["participant_id"]
    client.post(f"/participants/{pid}/constraints", json={"items": [], "budget_max_per_person": 1})       # absurdly low budget
    client.post(f"/participants/{pid}/preferences", json={"items": []})
    r = client.post(f"/sessions/{sid}/recommendations", json={"allow_partial": True}, params={"include_excluded": "true"}).json()
    assert r["excluded_count"] == 0 and r["eligible_count"] == r["pool_size"] == 15
    for t in r["top3"]:
        assert any(w["code"] == "price_unknown" and "價格資訊不足" in w["text"] for w in t["warnings"])


def test_restaurant_detail_shows_evidence_and_never_invents_safety(client):
    cands = client.post("/sessions", json={"title": "x", "party_size": 2}).json()
    sid = cands["session_id"]
    pid = client.post(f"/sessions/{sid}/participants", json={"line_user_id": "detail-" + sid}).json()["participant_id"]
    client.post(f"/participants/{pid}/constraints", json={"items": []})
    client.post(f"/participants/{pid}/preferences", json={"items": []})
    top = client.post(f"/sessions/{sid}/recommendations", json={"allow_partial": True}).json()["top3"]
    d = client.get(f"/restaurants/{top[0]['restaurant_id']}")
    assert d.status_code == 200
    body = d.json()
    assert body["name"] and body["notes"] and body["active_status"] == "unverified"
    assert all(a["state"] != "CONFIRMED_ABSENT" for a in body["attributes"]), "no real first-party absence evidence exists (test fixtures are hidden)"
    assert client.get(f"/restaurants/{uuid.uuid4()}").status_code == 404


def test_test_fixture_evidence_is_hidden_by_default(db):
    """seed_restaurants.sql contains 3 clearly fake first-party claims (source 7). They must be invisible unless explicitly enabled."""
    n = db.scalar(text("SELECT count(*) FROM enrichment.restaurant_attribute_state WHERE state = 'CONFIRMED_ABSENT'"))
    assert n == 0
    assert db.scalar(text("SELECT count(*) FROM enrichment.restaurant_attribute_evidence WHERE source_id = 7")) == 3


def test_meta_endpoints_feed_the_ui(client):
    attrs = client.get("/meta/attributes").json()
    codes = {i["attribute_code"] for g in attrs["groups"] for i in g["items"]}
    assert {"beef", "pork", "seafood", "shellfish", "offal", "raw_food", "peanut", "tree_nut", "milk", "egg", "sesame", "gluten", "vegetarian", "vegan", "halal", "gluten_free"} <= codes
    assert attrs["privacy_note"] == "其他人不會看到你的個人需求。"
    chips = client.get("/meta/cuisines").json()
    assert [c["tag"] for c in chips["chips"]][:3] == ["台式", "中式", "日式"] and len(chips["chips"]) == 15
    assert [s["stance"] for s in chips["stances"]] == ["love", "ok", "any", "dislike"]
    assert client.get("/meta/locations").json()["locations"][0]["key"] == "yancheng_pu"
    assert client.get("/healthz").json() == {"status": "ok"}


def test_twenty_plus_restaurants_integration(client, db, uniq):
    """The brief's integration test: 3 participants x 20+ restaurants -> Top 3. All 31 seed restaurants are forced into the pool for this test only."""
    before = dict(db.execute(select(Restaurant.restaurant_id, Restaurant.pool_status)).all())
    try:
        db.execute(text("UPDATE identity.restaurant SET pool_status = 'in_pool' WHERE pool_status = 'candidate'"))
        db.commit()
        demo = run_demo(client, user_prefix=uniq)
        r = demo["result"]
        assert r["pool_size"] == 31 and r["pool_size"] >= 20
        assert len(r["top3"]) == 3 and r["excluded_count"] + r["eligible_count"] == 31
        assert r["excluded_count"] >= 2
        assert not {t["name"] for t in r["top3"]} & {e["name"] for e in r["excluded"]}
    finally:
        for rid, status in before.items():
            db.execute(text("UPDATE identity.restaurant SET pool_status = :s WHERE restaurant_id = :r"), {"s": status, "r": rid})
        db.commit()
