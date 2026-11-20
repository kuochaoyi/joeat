"""User-testing feedback (Stitch prototype): party size 20, host, time poll, restaurant vote with sliders, editable answers, map coverage."""
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text

pytestmark = pytest.mark.integration
TAIPEI = timezone(timedelta(hours=8))


def slots(n=3, days=2):
    base = (datetime.now(TAIPEI) + timedelta(days=days)).replace(hour=18, minute=30, second=0, microsecond=0)
    return [(base + timedelta(hours=3 * i)).isoformat() for i in range(n)]


def make(client, *, uid=None, **kw):
    body = {"title": "t", "party_size": 3, "location_preset": "yancheng_pu", "host_line_user_id": uid or "host-" + uuid.uuid4().hex, **kw}
    r = client.post("/sessions", json=body)
    assert r.status_code == 201, r.text
    return r.json()


def join(client, sid, uid=None, label=None):
    return client.post(f"/sessions/{sid}/participants", json={"line_user_id": uid or "u-" + uuid.uuid4().hex, "label": label}).json()


# ------------------------------------------------------------------ party size and coverage
def test_party_size_up_to_20_and_the_cap_is_enforced(client, db):
    assert client.post("/sessions", json={"title": "big", "party_size": 20}).status_code == 201
    assert client.post("/sessions", json={"title": "big", "party_size": 21}).status_code == 422
    s = client.post("/sessions", json={"title": "full", "party_size": 2}).json()
    for _ in range(2):
        join(client, s["session_id"])
    assert client.post(f"/sessions/{s['session_id']}/participants", json={"line_user_id": "third"}).json()["error"] == "session_full"
    assert db.execute(text("SELECT count(*) FROM pg_constraint WHERE conname = 'session_party_size'")).scalar() == 1


def test_a_map_pin_outside_the_covered_district_is_allowed_but_flagged(client):
    near = client.post("/sessions", json={"title": "near", "meeting_lat": 22.6245, "meeting_lon": 120.2815, "location_label": "地圖選點"}).json()
    far = client.post("/sessions", json={"title": "far", "meeting_lat": 25.0478, "meeting_lon": 121.5170, "location_label": "台北車站"}).json()
    assert near["outside_coverage"] is False and far["outside_coverage"] is True
    assert client.post("/sessions", json={"title": "x", "meeting_lat": 35.68, "meeting_lon": 139.69}).json()["error"] == "outside_taiwan"
    assert client.post("/sessions", json={"title": "x", "meeting_lat": 22.6}).json()["error"] == "bad_coordinates"


# ------------------------------------------------------------------ edit answers
def test_answers_can_be_read_back_and_edited(client):
    s = make(client)
    p = join(client, s["session_id"])["participant_id"]
    client.post(f"/participants/{p}/constraints", json={"items": [{"attribute_code": "peanut", "reason": "allergy"}, {"attribute_code": "beef", "reason": "religion"}], "strict_allergy": True, "budget_max_per_person": 400})
    client.post(f"/participants/{p}/preferences", json={"items": [{"cuisine_tag": "日式", "stance": "love"}]})
    a = client.get(f"/participants/{p}/answers").json()
    assert a["strict_allergy"] is True and a["budget_max_per_person"] == 400 and a["constraints_submitted"] and a["preferences_submitted"]
    assert {(c["attribute_code"], c["reason"]) for c in a["constraints"]} == {("peanut", "allergy"), ("beef", "religion")}
    assert a["preferences"] == [{"cuisine_tag": "日式", "stance": "love"}]
    client.post(f"/participants/{p}/constraints", json={"items": []})                      # edit: now nothing
    assert client.get(f"/participants/{p}/answers").json()["constraints"] == []
    assert client.get(f"/participants/{uuid.uuid4()}/answers").status_code == 404


def test_europe_style_cuisine_exists_and_includes_italian(client, db):
    tags = [c["tag"] for c in client.get("/meta/cuisines").json()["chips"]]
    assert "歐式" in tags
    assert db.execute(text("SELECT parent_tag FROM ref.cuisine_tag WHERE tag = '義式'")).scalar() == "歐式"


# ------------------------------------------------------------------ time poll
def test_time_poll_members_choose_the_host_only_sets_the_deadline(client):
    s = make(client, time_mode="poll", time_slots=slots(3), time_deadline_hours=6)
    sid = s["session_id"]
    assert s["time_mode"] == "poll" and s["meal_time"] is None and s["time_closed"] is False and s["time_deadline"]
    member = join(client, sid)                                                            # not the host: a random member
    a, b = join(client, sid), join(client, sid)
    poll = client.get(f"/sessions/{sid}/time-poll", params={"participant_id": a["participant_id"]}).json()
    o = [x["option_id"] for x in poll["options"]]
    assert len(o) == 3 and all(x["count"] == 0 and not x["mine"] for x in poll["options"])
    client.put(f"/participants/{a['participant_id']}/time-votes", json={"option_ids": [o[1], o[2]]})
    after = client.put(f"/participants/{b['participant_id']}/time-votes", json={"option_ids": [o[1]]}).json()
    assert [x["count"] for x in after["options"]] == [0, 2, 1] and [x["mine"] for x in after["options"]] == [False, True, False]
    assert after["responded"] == 2 and "participant" not in str(after)                    # counts only, nobody's individual ticks
    assert client.put(f"/participants/{a['participant_id']}/time-votes", json={"option_ids": [999999]}).status_code == 422
    assert client.post(f"/sessions/{sid}/time-poll/close", json={"participant_id": member["participant_id"]}).json()["error"] == "host_only"


def test_the_host_can_close_the_poll_and_the_winning_slot_becomes_the_meal_time(client):
    uid = "host-" + uuid.uuid4().hex
    s = make(client, uid=uid, time_mode="poll", time_slots=slots(3))
    sid = s["session_id"]
    h = join(client, sid, uid=uid)
    assert h["is_host"] is True
    a = join(client, sid)
    assert a["is_host"] is False
    o = [x["option_id"] for x in client.get(f"/sessions/{sid}/time-poll").json()["options"]]
    client.put(f"/participants/{a['participant_id']}/time-votes", json={"option_ids": [o[2], o[1]]})
    client.put(f"/participants/{h['participant_id']}/time-votes", json={"option_ids": [o[2], o[0]]})
    closed = client.post(f"/sessions/{sid}/time-poll/close", json={"participant_id": h["participant_id"]}).json()
    assert closed["closed"] and closed["chosen_option_id"] == o[2] and closed["meal_time"]
    parse = lambda t: datetime.fromisoformat(t.replace("Z", "+00:00"))
    assert parse(client.get(f"/sessions/{sid}").json()["meal_time"]) == parse(closed["meal_time"])
    assert client.put(f"/participants/{a['participant_id']}/time-votes", json={"option_ids": [o[0]]}).json()["error"] == "poll_closed"


def test_the_poll_closes_by_itself_at_the_deadline_and_when_everyone_answered(client, db):
    s = make(client, time_mode="poll", time_slots=slots(2), party_size=2)
    sid = s["session_id"]
    a, b = join(client, sid), join(client, sid)
    o = [x["option_id"] for x in client.get(f"/sessions/{sid}/time-poll").json()["options"]]
    client.put(f"/participants/{a['participant_id']}/time-votes", json={"option_ids": [o[0]]})
    assert client.get(f"/sessions/{sid}/time-poll").json()["closed"] is False
    client.put(f"/participants/{b['participant_id']}/time-votes", json={"option_ids": [o[0], o[1]]})
    assert client.get(f"/sessions/{sid}/time-poll").json()["closed"] is True               # everyone expected has answered
    s2 = make(client, time_mode="poll", time_slots=slots(2))
    db.execute(text("UPDATE product.dining_session SET time_deadline = now() - interval '1 minute' WHERE session_id = :s"), {"s": s2["session_id"]})
    db.commit()
    assert client.get(f"/sessions/{s2['session_id']}").json()["time_closed"] is True       # deadline passed, nobody answered: closed without a winner
    assert client.get(f"/sessions/{s2['session_id']}").json()["meal_time"] is None


def test_poll_input_is_validated(client):
    assert client.post("/sessions", json={"title": "x", "time_mode": "poll", "time_slots": slots(1)}).json()["error"] == "poll_needs_options"
    assert client.post("/sessions", json={"title": "x", "time_mode": "fixed", "time_slots": slots(2)}).json()["error"] == "slots_need_poll"
    past = [(datetime.now(TAIPEI) - timedelta(days=3)).isoformat(), (datetime.now(TAIPEI) - timedelta(days=2)).isoformat()]
    assert client.post("/sessions", json={"title": "x", "time_mode": "poll", "time_slots": past}).json()["error"] == "slot_in_the_past"
    assert client.get(f"/sessions/{make(client)['session_id']}/time-poll").status_code == 404      # a fixed-time session has no poll


# ------------------------------------------------------------------ restaurant vote
def recommended_session(client, uid):
    s = make(client, uid=uid, party_size=3)
    sid = s["session_id"]
    host = join(client, sid, uid=uid)
    others = [join(client, sid) for _ in range(2)]
    for p in [host, *others]:
        client.post(f"/participants/{p['participant_id']}/constraints", json={"items": []})
        client.post(f"/participants/{p['participant_id']}/preferences", json={"items": [{"cuisine_tag": "台式", "stance": "love"}]})
    assert client.post(f"/sessions/{sid}/recommendations", json={}).status_code == 201
    return sid, host, others


def ballot(options, scores, any_ok=()):
    return [{"restaurant_id": o["restaurant_id"], "score": sc, "any_ok": i in any_ok} for i, (o, sc) in enumerate(zip(options, scores))]


def test_vote_with_sliders_hides_who_voted_what_and_picks_a_winner(client):
    uid = "host-" + uuid.uuid4().hex
    sid, host, (a, b) = recommended_session(client, uid)
    v = client.post(f"/sessions/{sid}/votes", json={"participant_id": host["participant_id"], "closes_in_hours": 12})
    assert v.status_code == 201
    vid = v.json()["vote_id"]
    opts = client.get(f"/sessions/{sid}/votes/current", params={"participant_id": a["participant_id"]}).json()["options"]
    assert len(opts) == 3 and [o["rank"] for o in opts] == [1, 2, 3] and all("name" in o and "warnings" in o for o in opts)
    assert client.post(f"/sessions/{sid}/votes", json={"participant_id": host["participant_id"]}).json()["error"] == "vote_open"      # one open vote at a time
    assert client.put(f"/votes/{vid}/ballot", json={"participant_id": a["participant_id"], "scores": ballot(opts[:2], [5, 5])}).json()["error"] == "incomplete_ballot"
    mid = client.put(f"/votes/{vid}/ballot", json={"participant_id": a["participant_id"], "scores": ballot(opts, [9, 2, 5], any_ok=(2,))}).json()
    assert mid["status"] == "open" and mid["voted"] == 1 and mid["result"] is None and mid["i_voted"] is True       # the aggregate stays hidden while open
    assert [o["my_score"] for o in mid["options"]] == [9, 2, 5] and mid["options"][2]["my_any_ok"] is True
    other_view = client.get(f"/sessions/{sid}/votes/current", params={"participant_id": b["participant_id"]}).json()
    assert other_view["i_voted"] is False and all(o["my_score"] is None for o in other_view["options"])               # nobody sees another person's ballot
    client.put(f"/votes/{vid}/ballot", json={"participant_id": b["participant_id"], "scores": ballot(opts, [7, 10, 5])})
    done = client.put(f"/votes/{vid}/ballot", json={"participant_id": host["participant_id"], "scores": ballot(opts, [8, 0, 5])}).json()
    assert done["status"] == "closed"                                                                                 # everybody voted: closes by itself
    res = {r["restaurant_id"]: r for r in done["result"]}
    assert res[opts[0]["restaurant_id"]]["total"] == 24 and res[opts[1]["restaurant_id"]]["total"] == 12
    assert done["winner_restaurant_id"] == opts[0]["restaurant_id"] and done["result"][0]["restaurant_id"] == opts[0]["restaurant_id"]
    assert res[opts[2]["restaurant_id"]]["any_ok"] == 1 and res[opts[1]["restaurant_id"]]["unhappy"] == 2
    assert client.put(f"/votes/{vid}/ballot", json={"participant_id": a["participant_id"], "scores": ballot(opts, [1, 1, 1])}).json()["error"] == "vote_closed"


def test_a_tie_goes_to_the_option_nobody_dislikes(client):
    uid = "host-" + uuid.uuid4().hex
    sid, host, (a, b) = recommended_session(client, uid)
    vid = client.post(f"/sessions/{sid}/votes", json={"participant_id": host["participant_id"]}).json()["vote_id"]
    opts = client.get(f"/sessions/{sid}/votes/current").json()["options"]
    # option 1: 10+0+6 = 16 (someone rated it 0); option 2: 5+5+6 = 16 (nobody below 5); option 3 trails
    for p, sc in ((host, [10, 5, 0]), (a, [0, 5, 0]), (b, [6, 6, 0])):
        client.put(f"/votes/{vid}/ballot", json={"participant_id": p["participant_id"], "scores": ballot(opts, sc)})
    final = client.get(f"/sessions/{sid}/votes/current").json()
    assert final["status"] == "closed" and final["winner_restaurant_id"] == opts[1]["restaurant_id"]
    assert final["tie_broken"] is False                                                   # decided by the lowest score, not by the rank fallback


def test_only_the_host_closes_or_starts_a_vote_and_needs_a_recommendation_first(client):
    uid = "host-" + uuid.uuid4().hex
    s = make(client, uid=uid)
    sid = s["session_id"]
    host = join(client, sid, uid=uid)
    assert client.post(f"/sessions/{sid}/votes", json={"participant_id": host["participant_id"]}).json()["error"] == "no_recommendation"
    sid2, host2, (m1, _) = recommended_session(client, "host-" + uuid.uuid4().hex)
    assert client.post(f"/sessions/{sid2}/votes", json={"participant_id": m1["participant_id"]}).json()["error"] == "host_only"
    vid = client.post(f"/sessions/{sid2}/votes", json={"participant_id": host2["participant_id"]}).json()["vote_id"]
    assert client.post(f"/votes/{vid}/close", json={"participant_id": m1["participant_id"]}).json()["error"] == "host_only"
    closed = client.post(f"/votes/{vid}/close", json={"participant_id": host2["participant_id"]}).json()
    assert closed["status"] == "closed" and closed["winner_restaurant_id"] is None      # nobody voted: no winner


def test_a_bot_created_session_has_no_host_so_any_member_may_start_the_vote(client):
    s = client.post("/sessions", json={"title": "bot", "party_size": 2, "location_preset": "yancheng_pu", "line_group_id": "Cgroup-" + uuid.uuid4().hex}).json()
    sid = s["session_id"]
    members = [join(client, sid) for _ in range(2)]
    for p in members:
        client.post(f"/participants/{p['participant_id']}/constraints", json={"items": []})
        client.post(f"/participants/{p['participant_id']}/preferences", json={"items": []})
    client.post(f"/sessions/{sid}/recommendations", json={})
    assert client.post(f"/sessions/{sid}/votes", json={"participant_id": members[0]["participant_id"]}).status_code == 201
