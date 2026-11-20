"""Dining type through the API: store only the type, read it back, group composition without names, and it never touches the recommendation."""
import uuid

import pytest
from sqlalchemy import text

from app.core import diet_type as d

pytestmark = pytest.mark.integration


def join(client, sid):
    return client.post(f"/sessions/{sid}/participants", json={"line_user_id": "u-" + uuid.uuid4().hex}).json()["participant_id"]


def take(client, pid, adv="AAA", flav="RRR", dist="WWW"):
    letters = list(adv) + list(flav) + list(dist)
    return client.put(f"/participants/{pid}/diet-type", json={"answers": {q["id"]: letters[i] for i, q in enumerate(d.QUESTIONS)}})


def test_quiz_meta_scoring_storage_and_retake(client, db):
    meta = client.get("/meta/diet-types").json()
    assert len(meta["questions"]) == 9 and len(meta["types"]) == 8 and [a["key"] for a in meta["axes"]] == ["adventure", "flavour", "distance"]
    sid = client.post("/sessions", json={"title": "q", "party_size": 3}).json()["session_id"]
    p = join(client, sid)
    r = take(client, p)
    assert r.status_code == 200 and r.json()["code"] == "ARW" and r.json()["name"] == "美食探險家" and "韓式" in r.json()["suggested_cuisines"]
    assert client.get(f"/participants/{p}/answers").json()["diet_type"] == "ARW"
    assert db.scalar(text("SELECT diet_type FROM product.participant WHERE participant_id = :p"), {"p": p}) == "ARW"
    assert take(client, p, "CCC", "LLL", "NNN").json()["code"] == "CLN"                    # retaking replaces it
    assert client.get(f"/participants/{p}/answers").json()["diet_type"] == "CLN"
    cols = {r[0] for r in db.execute(text("SELECT column_name FROM information_schema.columns WHERE table_schema='product' AND table_name='participant'"))}
    assert not any("answer" in c for c in cols)                                            # only the type is stored, never the answers


def test_bad_answers_are_refused(client):
    sid = client.post("/sessions", json={"title": "q"}).json()["session_id"]
    p = join(client, sid)
    assert client.put(f"/participants/{p}/diet-type", json={"answers": {"q1": "A"}}).json()["error"] == "bad_quiz_answers"
    assert client.put(f"/participants/{uuid.uuid4()}/diet-type", json={"answers": {}}).status_code == 404


def test_group_composition_is_counts_only_and_hidden_until_two_people_took_it(client):
    sid = client.post("/sessions", json={"title": "g", "party_size": 4}).json()["session_id"]
    a, b, c = join(client, sid), join(client, sid), join(client, sid)
    assert client.get(f"/sessions/{sid}/diet-types").json()["hidden"] is True
    take(client, a)
    assert client.get(f"/sessions/{sid}/diet-types").json()["hidden"] is True              # one person: it would identify them
    take(client, b)
    take(client, c, "CCC", "LLL", "NNN")
    g = client.get(f"/sessions/{sid}/diet-types").json()
    assert g["hidden"] is False and g["taken"] == 3 and g["joined"] == 3
    assert [(t["code"], t["count"]) for t in g["types"]] == [("ARW", 2), ("CLN", 1)]
    assert not any(str(x) in str(g) for x in (a, b, c))                                    # nobody's id, nobody's name


def test_the_type_never_changes_the_recommendation(client):
    def run(with_type):
        sid = client.post("/sessions", json={"title": "r", "party_size": 2, "location_preset": "yancheng_pu"}).json()["session_id"]
        ps = [join(client, sid) for _ in range(2)]
        for p in ps:
            client.post(f"/participants/{p}/constraints", json={"items": [{"attribute_code": "peanut", "reason": "allergy"}]})
            client.post(f"/participants/{p}/preferences", json={"items": [{"cuisine_tag": "台式", "stance": "love"}]})
            if with_type:
                take(client, p)
        r = client.post(f"/sessions/{sid}/recommendations", json={}).json()
        return [(t["name"], t["score"]["total"]) for t in r["top3"]], r["excluded_count"]
    assert run(False) == run(True)
