"""Recommendation integration rules (docs/decisions/0001-merchant-declaration.md, D2-D4): preference softening, strict allergy mode,
and the factual wording of declarations. Pure functions: no database."""
import pytest

from app.core.merchant_form import FORBIDDEN_WORDS
from app.recommendation.engine import CandidateResult, RestaurantInput
from app.recommendation.explain import attribute_warnings, declaration_statements
from app.recommendation.hard_filter import effective_class, evaluate_restaurant
from tests.helpers import ATTRS, REASON_CLASS, REASON_RISK, RULES, c, restaurant, st


def run(constraints, states):
    return evaluate_restaurant("r1", constraints, ATTRS, REASON_RISK, states, RULES, REASON_CLASS)


def cand(constraints, states) -> CandidateResult:
    return CandidateResult(restaurant=restaurant("r1", states=states), stage="eligible", filter=run(constraints, states))


# ------------------------------------------------------------------ safety vs preference (D3)
def test_effective_class_comes_from_the_reason_then_the_attribute_default():
    assert effective_class("religion", ATTRS["beef"], REASON_CLASS) == "safety"            # religion is a safety constraint (product decision)
    assert effective_class("dislike", ATTRS["peanut"], REASON_CLASS) == "preference"       # the member's own reason wins
    assert effective_class("unspecified", ATTRS["peanut"], REASON_CLASS) == "safety"       # no reason: allergens default to safety
    assert effective_class("unspecified", ATTRS["beef"], REASON_CLASS) == "preference"


@pytest.mark.parametrize("state", ["CONFIRMED_PRESENT", "LIKELY_PRESENT"])
def test_some_dishes_only_warns_for_a_preference_constraint(state):
    res = run([c("A", "beef", "dislike")], {"beef": st(state, 1, declared=True, presence_extent="some")})
    chk = res.checks[0]
    assert res.eligible is True
    assert (chk.action, chk.warning_level, chk.engine_note) == ("WARN", "high", "softened_some")
    assert chk.evidence_snapshot["engine_note"] == "softened_some"                          # the audit row says why it was not excluded


@pytest.mark.parametrize("extent", ["most", None])
def test_most_or_unknown_extent_still_excludes_a_preference_constraint(extent):
    assert run([c("A", "beef", "dislike")], {"beef": st("CONFIRMED_PRESENT", 1, presence_extent=extent)}).eligible is False


def test_some_dishes_never_softens_a_safety_constraint():
    assert run([c("A", "beef", "religion")], {"beef": st("CONFIRMED_PRESENT", 1, presence_extent="some")}).eligible is False
    assert run([c("A", "beef", "allergy")], {"beef": st("CONFIRMED_PRESENT", 1, presence_extent="some")}).eligible is False


def test_some_dishes_never_softens_a_critical_attribute_even_if_the_member_says_dislike():
    assert run([c("A", "peanut", "dislike")], {"peanut": st("CONFIRMED_PRESENT", 1, presence_extent="some")}).eligible is False


def test_softening_is_not_applied_to_require_constraints():
    res = run([c("A", "vegetarian", "belief_diet")], {"vegetarian": st("CONFIRMED_ABSENT", 1, presence_extent="some")})
    assert res.eligible is False


# ------------------------------------------------------------------ strict allergy mode
@pytest.mark.parametrize("state", ["UNKNOWN", "LIKELY_ABSENT"])
def test_strict_mode_excludes_anything_not_confirmed_absent(state):
    loose = run([c("A", "peanut", "allergy")], {"peanut": st(state, 1)})
    strict = run([c("A", "peanut", "allergy", strict=True)], {"peanut": st(state, 1)})
    assert loose.eligible is True and strict.eligible is False
    assert strict.checks[0].engine_note == "strict_allergy" and strict.exclusion_reasons[0]["message"] == "花生：沒有店家確認"


def test_strict_mode_passes_a_confirmed_absence_and_still_excludes_presence():
    assert run([c("A", "peanut", "allergy", strict=True)], {"peanut": st("CONFIRMED_ABSENT", 1)}).eligible is True
    assert run([c("A", "peanut", "allergy", strict=True)], {"peanut": st("LIKELY_PRESENT", 1)}).eligible is False


def test_strict_mode_with_no_evidence_at_all_excludes():
    assert run([c("A", "peanut", "allergy", strict=True)], {}).eligible is False


def test_strict_mode_only_governs_the_members_own_safety_constraints():
    # a strict member's dislike (preference) is not tightened, and another member's non-strict allergy is not either
    states = {"beef": st("UNKNOWN"), "peanut": st("UNKNOWN")}
    assert run([c("A", "beef", "dislike", strict=True)], states).eligible is True
    assert run([c("A", "beef", "dislike", strict=True), c("B", "peanut", "allergy")], states).eligible is True
    assert run([c("A", "beef", "dislike", strict=True), c("B", "peanut", "allergy", strict=True)], states).eligible is False


def test_strict_mode_does_not_touch_require_constraints():
    assert run([c("A", "gluten_free", "medical", strict=True)], {"gluten_free": st("UNKNOWN")}).eligible is True


# ------------------------------------------------------------------ wording (D2, D4)
def test_possible_and_unknown_shared_equipment_read_differently_and_neither_claims_safety():
    possible = cand([c("A", "peanut", "allergy")], {"peanut": st("LIKELY_ABSENT", 1, declared=True, cross_contact="possible", verified_on="2026-11-02")})
    unknown = cand([c("A", "peanut", "allergy")], {"peanut": st("LIKELY_ABSENT", 1, declared=True, cross_contact="unknown", verified_on="2026-11-02")})
    nothing = cand([c("A", "peanut", "allergy")], {})
    wp, wu, wn = (attribute_warnings(x, ATTRS)[0] for x in (possible, unknown, nothing))
    assert wp["code"] == "attribute_cross_contact_possible" and "可能有交叉接觸" in wp["text"]
    assert wu["code"] == "attribute_declared_shared_unknown" and "共用設備資訊：未知" in wu["text"]
    assert wn["code"] == "attribute_unknown" and "資訊不足" in wn["text"]
    assert wp["level"] == wu["level"] == wn["level"] == "critical"                          # a declaration never lowers the warning level
    for w in (wp, wu, wn):
        assert not any(word in w["text"] for word in FORBIDDEN_WORDS)


def test_declaration_statement_is_a_dated_fact_in_the_decided_wording():
    confirmed = cand([c("A", "peanut", "allergy")], {"peanut": st("CONFIRMED_ABSENT", 1, declared=True, cross_contact="confirmed_none", verified_on="2026-11-02")})
    [d] = declaration_statements(confirmed, ATTRS)
    assert d["text"].startswith("店家於 2026/11/02 聲明其目前菜單未使用花生；共用設備資訊：確認沒有共用")
    assert d["verified"] is True and "人工驗證" in d["text"]
    likely = cand([c("A", "peanut", "allergy")], {"peanut": st("LIKELY_ABSENT", 1, declared=True, cross_contact="unknown", verified_on="2026-11-02")})
    [d] = declaration_statements(likely, ATTRS)
    assert "共用設備資訊：未知" in d["text"] and d["verified"] is False and "尚未列為「已確認」" in d["text"]


def test_declaration_statements_never_contain_forbidden_words_and_skip_non_declarations():
    states = {"peanut": st("CONFIRMED_ABSENT", 1, declared=True, cross_contact="confirmed_none", verified_on="2026-11-02"),
              "beef": st("CONFIRMED_PRESENT", 2, declared=True, presence_extent="some", verified_on="2026-11-02"),
              "pork": st("CONFIRMED_ABSENT", 3)}                                         # first-party but not a declaration: no statement
    out = declaration_statements(cand([c("A", "peanut", "allergy"), c("A", "beef", "dislike"), c("A", "pork")], states), ATTRS)
    assert [d["attribute"] for d in out] == ["beef", "peanut"]
    beef = out[0]
    assert "有些餐點含有牛肉" in beef["text"]
    for d in out:
        assert not any(word in d["text"] for word in FORBIDDEN_WORDS)


def test_softened_warning_names_the_attribute_and_not_the_person():
    x = cand([c("A", "beef", "dislike")], {"beef": st("CONFIRMED_PRESENT", 1, declared=True, presence_extent="some")})
    w = attribute_warnings(x, ATTRS)[0]
    assert w["code"] == "attribute_present_some" and w["level"] == "high" and "可選擇不含的餐點" in w["text"]


def test_the_statement_date_is_the_merchants_declaration_date_not_the_publish_date():
    x = cand([c("A", "peanut", "allergy")], {"peanut": st("CONFIRMED_ABSENT", 1, declared=True, cross_contact="confirmed_none", verified_on="2026-11-04", declared_on="2026-11-01")})
    [d] = declaration_statements(x, ATTRS)
    assert d["text"].startswith("店家於 2026/11/01 聲明") and "2026/11/04" not in d["text"]
    legacy = cand([c("A", "peanut", "allergy")], {"peanut": st("CONFIRMED_ABSENT", 1, declared=True, cross_contact="confirmed_none", verified_on="2026-11-04")})
    assert declaration_statements(legacy, ATTRS)[0]["text"].startswith("店家於 2026/11/04 聲明")        # rows without a declaration date fall back
