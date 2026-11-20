from app.recommendation.hard_filter import effective_risk, evaluate_restaurant, filter_restaurants
from tests.helpers import ATTRS, REASON_RISK, RULES, c, st


def run(constraints, states, rid="r1"):
    return evaluate_restaurant(rid, constraints, ATTRS, REASON_RISK, states, RULES)


# ---- the three cases required by the brief -------------------------------------------------------------------------
def test_confirmed_present_excludes():
    res = run([c("A", "beef")], {"beef": st("CONFIRMED_PRESENT", 7)})
    assert res.eligible is False
    assert res.exclusion_reasons[0]["attribute"] == "beef"
    assert res.exclusion_reasons[0]["reason"] == "CONFIRMED_PRESENT"


def test_unknown_warns_but_does_not_exclude():
    res = run([c("B", "peanut", "allergy")], {})            # no evidence at all == UNKNOWN
    assert res.eligible is True
    assert res.exclusion_reasons == []
    assert res.unknown_warnings[0]["attribute"] == "peanut" and res.unknown_warnings[0]["reason"] == "UNKNOWN"
    assert res.unknown_warnings[0]["level"] == "critical"
    assert res.to_dict()["warnings"] == [{"attribute": "peanut", "reason": "UNKNOWN", "level": "critical", "message": "花生：資料不足，無法確認，請向店家確認"}]


def test_require_attribute_confirmed_absent_excludes():
    res = run([c("C", "vegetarian", "belief_diet")], {"vegetarian": st("CONFIRMED_ABSENT", 3)})
    assert res.eligible is False
    assert res.exclusion_reasons[0]["attribute"] == "vegetarian"


# ---- more of the contract ------------------------------------------------------------------------------------------
def test_likely_absent_is_not_safe_for_a_critical_allergen():
    res = run([c("B", "peanut", "allergy")], {"peanut": st("LIKELY_ABSENT", 1)})
    chk = res.checks[0]
    assert res.eligible is True
    assert chk.action == "WARN" and chk.warning_level == "critical" and chk.may_show_safe_badge is False
    assert res.unknown_warnings, "LIKELY_ABSENT must be reported like UNKNOWN"


def test_only_confirmed_absent_gives_a_safe_badge():
    res = run([c("B", "peanut", "allergy")], {"peanut": st("CONFIRMED_ABSENT", 9)})
    assert res.checks[0].action == "PASS" and res.checks[0].may_show_safe_badge is True
    assert res.warnings == []


def test_likely_present_critical_is_excluded_but_normal_risk_only_warns():
    assert run([c("B", "peanut", "allergy")], {"peanut": st("LIKELY_PRESENT", 1)}).eligible is False
    res = run([c("A", "offal")], {"offal": st("LIKELY_PRESENT", 2)})           # offal: normal risk
    assert res.eligible is True and res.checks[0].action == "WARN" and res.checks[0].warning_level == "high"


def test_reason_can_raise_but_never_lower_risk():
    assert effective_risk("normal", "critical") == "critical"
    assert effective_risk("critical", "normal") == "critical"
    # offal is normal risk, but declared as an allergy -> critical -> LIKELY_PRESENT now excludes
    assert run([c("A", "offal", "allergy")], {"offal": st("LIKELY_PRESENT", 2)}).eligible is False


def test_require_likely_present_is_conditional_pass():
    res = run([c("C", "vegetarian", "belief_diet")], {"vegetarian": st("LIKELY_PRESENT", 5)})
    assert res.eligible and res.checks[0].action == "PASS_CONDITIONAL"
    assert res.checks[0].may_show_safe_badge is False


def test_require_unknown_keeps_with_warning_and_likely_absent_excludes():
    assert run([c("C", "vegetarian", "belief_diet")], {}).checks[0].action == "WARN"
    assert run([c("C", "vegetarian", "belief_diet")], {"vegetarian": st("LIKELY_ABSENT", 5)}).eligible is False


def test_one_participants_exclusion_excludes_for_the_group():
    res = run([c("A", "beef"), c("B", "peanut", "allergy"), c("C", "pork")], {"beef": st("CONFIRMED_PRESENT", 1)})
    assert res.eligible is False
    assert {w["attribute"] for w in res.unknown_warnings} == {"peanut", "pork"}      # still recorded for the audit trail


def test_no_constraints_means_eligible_without_warnings():
    res = run([], {})
    assert res.eligible and res.warnings == [] and res.checks == []


def test_output_never_contains_participant_ids():
    d = run([c("participant-A", "beef"), c("participant-B", "peanut", "allergy")], {"beef": st("CONFIRMED_PRESENT", 1)}).to_dict()
    assert "participant" not in str(d).lower()


def test_filter_restaurants_splits_eligible_and_excluded():
    eligible, excluded = filter_restaurants(
        {"ok": {}, "bad": {"beef": st("CONFIRMED_PRESENT", 1)}}, [c("A", "beef")], ATTRS, REASON_RISK, RULES)
    assert [r.restaurant_id for r in eligible] == ["ok"] and [r.restaurant_id for r in excluded] == ["bad"]
