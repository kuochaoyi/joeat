from app.recommendation.engine import EngineInput, run_engine
from app.recommendation.explain import build_explanation
from app.recommendation.ranking import RankInput, rank
from app.recommendation.rules import DEFAULT_RULES
from app.recommendation.scoring import DEFAULT_CONFIG
from tests.helpers import ATTRS, REASON_RISK, RULES, c, restaurant, st


def ri(rid, total, crit=0, warn=0, dist=100):
    return RankInput(rid, total, crit, warn, dist)


# ---- Top 3 sorting -------------------------------------------------------------------------------------------------
def test_top3_sorted_by_score_descending():
    top = rank([ri("a", 1), ri("b", 5), ri("c", 3), ri("d", 4)], 3)
    assert [t.restaurant_id for t in top] == ["b", "d", "c"]


def test_ties_prefer_fewer_critical_warnings_then_fewer_warnings_then_nearer():
    top = rank([ri("far", 5, 0, 1, 900), ri("crit", 5, 1, 0, 10), ri("warn2", 5, 0, 2, 10), ri("near", 5, 0, 1, 100)], 4)
    assert [t.restaurant_id for t in top] == ["near", "far", "warn2", "crit"]


def test_unknown_distance_sorts_after_known_and_ids_make_it_deterministic():
    top = rank([ri("z", 5, dist=None), ri("b", 5, dist=50), ri("a", 5, dist=50)], 3)
    assert [t.restaurant_id for t in top] == ["a", "b", "z"]


def test_fewer_than_three_candidates_returns_what_exists():
    assert len(rank([ri("a", 1), ri("b", 2)], 3)) == 2 and rank([], 3) == []


# ---- engine --------------------------------------------------------------------------------------------------------
def make_input(restaurants, constraints, preferences, any_budget=False):
    return EngineInput(restaurants=restaurants, constraints=constraints, preferences=preferences, attributes=ATTRS, reason_min_risk=REASON_RISK,
                       rules=DEFAULT_RULES, config=DEFAULT_CONFIG, meeting_lat=22.62416, meeting_lon=120.28408, any_budget=any_budget)


def test_excluded_restaurants_are_returned_but_never_scored_or_ranked():
    out = run_engine(make_input(
        [restaurant("beefy", states={"beef": st("CONFIRMED_PRESENT", 1)}), restaurant("fine")], [c("A", "beef")], {"A": {"台式": "love"}}))
    by = {x.restaurant.restaurant_id: x for x in out.candidates}
    assert by["beefy"].stage == "excluded" and by["beefy"].score is None and by["beefy"].rank is None
    assert by["fine"].stage == "top3" and by["fine"].rank == 1
    assert [x.restaurant.restaurant_id for x in out.top] == ["fine"]


def test_engine_warnings_count_attribute_and_non_attribute_notes():
    out = run_engine(make_input([restaurant("r", hours="none", lat=None, lon=None)], [c("B", "peanut", "allergy")], {"B": {}}, any_budget=True))
    cand = out.candidates[0]
    codes = {w["code"] for w in cand.warnings}
    assert codes == {"distance_unknown", "hours_unknown", "price_unknown"}
    assert cand.critical_warning_count == 1 and cand.warning_count == 1 + 3
    assert cand.score.distance_score == 0, "unknown distance is neutral, never a penalty"


def test_budget_never_excludes_and_adds_no_points():
    with_budget = run_engine(make_input([restaurant("r")], [], {}, any_budget=True)).candidates[0]
    without = run_engine(make_input([restaurant("r")], [], {}, any_budget=False)).candidates[0]
    assert with_budget.stage != "excluded" and with_budget.score.total_score == without.score.total_score


def test_demo_scenario_in_pure_form():
    """A: no beef, likes Japanese. B: peanut allergy, likes hotpot. C: anything."""
    prefs = {"A": {"日式": "love"}, "B": {"火鍋": "love"}, "C": {}}
    cons = [c("A", "beef"), c("B", "peanut", "allergy")]
    rs = [restaurant("beef_noodle", tags=[("台式", None)], states={"beef": st("CONFIRMED_PRESENT", 1)}),
          restaurant("jp", tags=[("日式", None)]), restaurant("hotpot", tags=[("火鍋", None)]),
          restaurant("peanut_zongzi", tags=[("小吃", None)], states={"peanut": st("LIKELY_PRESENT", 2)}),
          restaurant("plain", tags=[("台式", None)])]
    out = run_engine(make_input(rs, cons, prefs))
    ids = {x.restaurant.restaurant_id: x for x in out.candidates}
    assert ids["beef_noodle"].stage == "excluded" and ids["peanut_zongzi"].stage == "excluded"
    assert {x.restaurant.restaurant_id for x in out.top} == {"jp", "hotpot", "plain"}
    assert [x.restaurant.restaurant_id for x in out.top][-1] == "plain"
    assert ids["jp"].score.cuisine_score == 3 and ids["hotpot"].score.cuisine_score == 3
    for x in out.top:                                           # peanut data is UNKNOWN everywhere -> every Top 3 entry carries the warning
        assert any(w["attribute"] == "peanut" and w["level"] == "critical" for w in build_explanation(x, prefs, ATTRS)["attribute_warnings"])


# ---- explanation wording / privacy ---------------------------------------------------------------------------------
def test_explanation_is_group_level_and_never_claims_safety():
    prefs = {"A": {"日式": "love"}, "B": {"日式": "ok"}, "C": {"日式": "any"}}
    out = run_engine(make_input([restaurant("jp", tags=[("日式", None)], hours="none")], [c("B", "peanut", "allergy")], prefs))
    ex = build_explanation(out.candidates[0], prefs, ATTRS)
    texts = " ".join(r["text"] for r in ex["reasons"])
    assert "2/3 人偏好日式" in texts
    assert "花生資訊不足，建議向店家確認" in [w["text"] for w in ex["attribute_warnings"]]
    assert "安全" not in texts and "確認不含" not in texts
    assert ex["hard_constraint"]["status"] == "no_known_conflict" and ex["hard_constraint"]["unknown_attributes"] == ["花生"]
    assert not any("participant" in k for k in ex)
    assert {n["code"] for n in ex["notes"]} >= {"hours_unknown", "status_unverified"}


def test_rule_matrix_invariants():
    assert len(RULES) == 30
    for (typ, risk, state), rule in RULES.items():
        if rule.may_show_safe_badge:
            assert (typ, state) in {("avoid", "CONFIRMED_ABSENT"), ("require", "CONFIRMED_PRESENT")}
        if typ == "avoid" and risk == "critical" and state in ("UNKNOWN", "LIKELY_ABSENT"):
            assert rule.action == "WARN" and rule.warning_level == "critical" and not rule.may_show_safe_badge
        if rule.action == "EXCLUDE":
            assert rule.warning_level == "none"
