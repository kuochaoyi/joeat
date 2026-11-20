"""The Python engine (used by the API) and the SQL reference engine (product.evaluate_session in schema_v2.sql, validated earlier)
must agree on every decision: same exclusions, scores, warnings, ranks and audit rows. Two independent implementations of the
same contract make drift visible."""
import uuid

import pytest
from sqlalchemy import select, text

from app.demo_scenario import run_demo
from app.models.product import RecommendationCandidate, RecommendationConstraintCheck, RecommendationScoreComponent
from app.recommendation.rules import DEFAULT_RULES
from app.services import recommendations as rec

pytestmark = pytest.mark.integration


def snapshot(db, run_id):
    cands = {c.restaurant_id: (c.stage, c.rank, c.cuisine_score and float(c.cuisine_score), c.distance_score and float(c.distance_score),
                               c.data_confidence_score and float(c.data_confidence_score), c.total_score and float(c.total_score), c.warning_count,
                               c.critical_warning_count, [] if c.stage == "excluded" else sorted(w["code"] for w in (c.warnings or [])))   # SQL also fills hours/distance notes for excluded rows; they are never shown
             for c in db.scalars(select(RecommendationCandidate).where(RecommendationCandidate.run_id == run_id))}
    checks = sorted((k.restaurant_id, k.participant_id, k.attribute_code, k.effective_risk_level, k.evidence_state, k.action, k.warning_level, k.may_show_safe_badge, k.deciding_evidence_id)
                    for k in db.scalars(select(RecommendationConstraintCheck).where(RecommendationConstraintCheck.run_id == run_id)))
    comps = sorted((x.restaurant_id, x.component, x.participant_id or uuid.UUID(int=0), float(x.points))
                   for x in db.scalars(select(RecommendationScoreComponent).where(RecommendationScoreComponent.run_id == run_id)))
    return cands, checks, comps


def assert_same(db, python_run, session_id):
    sql_run = db.scalar(text("SELECT product.evaluate_session(:s)"), {"s": session_id})
    db.commit()
    py, sq = snapshot(db, uuid.UUID(python_run)), snapshot(db, sql_run)
    assert py[0] == sq[0], "candidate stage / rank / scores / warnings differ"
    assert py[1] == sq[1], "constraint-check audit rows differ"
    assert py[2] == sq[2], "score components differ"
    assert len(py[0]) >= 15


def test_rule_matrix_in_database_equals_the_code_copy(db):
    assert rec.load_rules(db) == DEFAULT_RULES


def test_python_and_sql_engines_agree_on_the_demo_scenario(client, db, uniq):
    demo = run_demo(client, user_prefix=uniq)
    assert_same(db, demo["result"]["run_id"], uuid.UUID(demo["session"]["session_id"]))


def test_python_and_sql_engines_agree_on_a_messy_scenario(client, db, uniq):
    """4 people, mixed risk levels, a require-type constraint, a budget, parent-tag preference and dislikes."""
    s = client.post("/sessions", json={"title": "messy", "party_size": 4, "location_preset": "pier2_dayi"}).json()["session_id"]
    ids = [client.post(f"/sessions/{s}/participants", json={"line_user_id": f"{uniq}-{i}", "label": str(i)}).json()["participant_id"] for i in range(4)]
    plan = [
        ([{"attribute_code": "pork"}, {"attribute_code": "offal", "reason": "allergy"}], [("中式", "love"), ("甜點", "dislike")]),
        ([{"attribute_code": "vegetarian", "reason": "belief_diet"}], [("素食", "love"), ("台式", "ok"), ("小吃", "dislike")]),
        ([{"attribute_code": "seafood"}, {"attribute_code": "tree_nut"}, {"attribute_code": "soy"}], [("日式", "ok"), ("早午餐", "love")]),
        ([], [("咖啡廳", "love"), ("台式", "any")]),
    ]
    for pid, (cons, prefs) in zip(ids, plan):
        client.post(f"/participants/{pid}/constraints", json={"items": cons, **({"budget_max_per_person": 300} if pid == ids[1] else {})})
        client.post(f"/participants/{pid}/preferences", json={"items": [{"cuisine_tag": t, "stance": st} for t, st in prefs]})
    run = client.post(f"/sessions/{s}/recommendations").json()
    assert run["top3"], "the scenario must still produce recommendations"
    assert_same(db, run["run_id"], uuid.UUID(s))
