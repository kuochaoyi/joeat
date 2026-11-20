"""Group needs (a pet / a child) chosen by the host: declared by merchants, applied by the real engine, shown per restaurant."""
import uuid

import pytest
from sqlalchemy import text

from tests.integration._merchant_helpers import H, submitted_declaration

pytestmark = pytest.mark.integration


@pytest.fixture()
def env(merchant_env, client, db):
    return client, db


def declare(client, db, name, answers):
    _, d = submitted_declaration(client, db, name, answers)
    assert client.post(f"/ops/declarations/{d}/publish", headers=H).status_code == 200


def make_session(client, uid, **needs):
    s = client.post("/sessions", json={"title": "n", "party_size": 2, "location_preset": "yancheng_pu", "host_line_user_id": uid, **needs}).json()
    sid = s["session_id"]
    host = client.post(f"/sessions/{sid}/participants", json={"line_user_id": uid}).json()
    other = client.post(f"/sessions/{sid}/participants", json={"line_user_id": "o-" + uuid.uuid4().hex}).json()
    for p in (host, other):
        client.post(f"/participants/{p['participant_id']}/constraints", json={"items": []})
        client.post(f"/participants/{p['participant_id']}/preferences", json={"items": []})
    return s, host, other


def run(client, sid):
    r = client.post(f"/sessions/{sid}/recommendations?include_excluded=true", json={})
    assert r.status_code == 201, r.text
    return r.json()


def explanation(db, run_id, name):
    return db.scalar(text("SELECT c.explanation FROM product.recommendation_candidate c JOIN identity.restaurant r USING (restaurant_id) WHERE c.run_id = :run AND r.canonical_name = :n"),
                     {"run": run_id, "n": name})


def test_the_host_picks_the_needs_and_a_refusing_restaurant_is_excluded_but_a_child_need_only_warns(env):
    client, db = env
    declare(client, db, "鴨肉珍", {"pets_allowed": "not_offered"})                 # explicit refusal (strong verification -> confirmed absent)
    declare(client, db, "東京小城", {"pets_allowed": "offered"})                    # confirmed present
    declare(client, db, "蟳市長", {"kid_friendly": "not_offered"})                  # no child seats
    s, host, other = make_session(client, "host-" + uuid.uuid4().hex, needs_pets=True, needs_kids=True)
    assert s["needs_pets"] is True and s["needs_kids"] is True
    resp = run(client, s["session_id"])
    excluded = {e["name"]: e["reasons"] for e in resp["excluded"]}
    assert "鴨肉珍" in excluded and "可攜寵物：店家表示不可攜帶寵物入內" in excluded["鴨肉珍"]        # a refused pet = excluded
    assert "蟳市長" not in excluded                                                         # a refused child need = a warning only
    ex = explanation(db, resp["run_id"], "東京小城")
    pets = [n for n in ex["needs"] if n["code"] == "pets"][0]
    assert pets["status"] == "yes" and pets["text"].startswith("店家於 ") and "聲明可攜帶寵物入內" in pets["text"]
    kids = [n for n in explanation(db, resp["run_id"], "蟳市長")["needs"] if n["code"] == "kids"][0]
    assert kids["status"] == "no" and "不會排除這家店" in kids["text"]
    unknown = [n for n in explanation(db, resp["run_id"], "阿英排骨飯")["needs"]]
    assert {n["code"]: n["status"] for n in unknown} == {"pets": "unknown", "kids": "unknown"}          # no data: a warning, never an exclusion
    assert "阿英排骨飯" not in excluded
    # the needs never leak into the food-safety wording
    assert all(w["attribute"] not in ("pets_allowed", "kid_friendly") for w in explanation(db, resp["run_id"], "阿英排骨飯")["attribute_warnings"])


def test_without_the_needs_nothing_changes(env):
    client, db = env
    s, *_ = make_session(client, "host-" + uuid.uuid4().hex)
    resp = run(client, s["session_id"])
    assert "鴨肉珍" not in [e["name"] for e in resp["excluded"]]
    assert explanation(db, resp["run_id"], "東京小城")["needs"] == []
    assert all(t["needs"] == [] for t in resp["top3"])


def test_only_the_host_changes_the_needs_and_it_applies_to_the_next_run(env):
    client, db = env
    s, host, other = make_session(client, "host-" + uuid.uuid4().hex)
    sid = s["session_id"]
    assert client.put(f"/sessions/{sid}/needs", json={"participant_id": other["participant_id"], "needs_pets": True, "needs_kids": False}).json()["error"] == "host_only"
    ok = client.put(f"/sessions/{sid}/needs", json={"participant_id": host["participant_id"], "needs_pets": True, "needs_kids": False})
    assert ok.status_code == 200 and ok.json() == {"needs_pets": True, "needs_kids": False}
    got = client.get(f"/sessions/{sid}").json()
    assert got["needs_pets"] is True and got["needs_kids"] is False
    resp = run(client, sid)
    assert "鴨肉珍" in [e["name"] for e in resp["excluded"]]                               # refused pets (declared in the first test of this module)


def test_a_vote_card_carries_the_needs(env):
    client, db = env
    s, host, other = make_session(client, "host-" + uuid.uuid4().hex, needs_pets=True)
    sid = s["session_id"]
    run(client, sid)
    v = client.post(f"/sessions/{sid}/votes", json={"participant_id": host["participant_id"]})
    assert v.status_code == 201
    opts = client.get(f"/sessions/{sid}/votes/current").json()["options"]
    assert all(any(n["name"] == "攜帶寵物" for n in o["needs"]) for o in opts)
