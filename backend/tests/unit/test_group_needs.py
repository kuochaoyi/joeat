"""Group needs chosen by the host (a pet / a child): the pet need excludes only on an explicit refusal, the child need only ever warns."""
import pytest

from app.core.merchant_form import FORBIDDEN_WORDS, describe, form_spec
from app.recommendation.engine import CandidateResult
from app.recommendation.explain import attribute_warnings, declaration_statements, need_items
from app.recommendation.hard_filter import evaluate_restaurant
from app.recommendation.types import AttributeInfo, Constraint
from tests.helpers import ATTRS, REASON_CLASS, REASON_RISK, RULES, restaurant, st

NEED_ATTRS = {**ATTRS,
              "pets_allowed": AttributeInfo("pets_allowed", "可攜寵物", "require", "normal"),
              "kid_friendly": AttributeInfo("kid_friendly", "親子友善", "require", "normal")}
PET = Constraint("p", "pets_allowed", "unspecified", False, False)
KID = Constraint("p", "kid_friendly", "unspecified", False, True)


def run(constraints, states):
    return evaluate_restaurant("r1", constraints, NEED_ATTRS, REASON_RISK, states, RULES, REASON_CLASS)


def cand(constraints, states):
    return CandidateResult(restaurant=restaurant("r1", states=states), stage="eligible", filter=run(constraints, states))


# ------------------------------------------------------------------ rules
def test_a_restaurant_that_explicitly_refuses_pets_is_excluded():
    res = run([PET], {"pets_allowed": st("CONFIRMED_ABSENT", 1)})
    assert res.eligible is False and res.exclusion_reasons[0]["message"] == "可攜寵物：店家表示不可攜帶寵物入內"


def test_unknown_or_unconfirmed_pet_policy_only_warns():
    res = run([PET], {})
    assert res.eligible is True and res.checks[0].action == "WARN"
    assert run([PET], {"pets_allowed": st("LIKELY_ABSENT", 1)}).eligible is True            # not confirmed: a warning, not an exclusion


def test_pets_allowed_passes():
    assert run([PET], {"pets_allowed": st("CONFIRMED_PRESENT", 1)}).checks[0].action == "PASS"


def test_a_child_need_never_excludes_even_when_the_restaurant_says_no():
    res = run([KID], {"kid_friendly": st("CONFIRMED_ABSENT", 1, declared=True, verified_on="2026-11-04")})
    chk = res.checks[0]
    assert res.eligible is True and (chk.action, chk.warning_level, chk.engine_note) == ("WARN", "normal", "soft_need")
    assert chk.evidence_snapshot["engine_note"] == "soft_need"
    assert run([KID], {"kid_friendly": st("CONFIRMED_PRESENT", 1)}).checks[0].action == "PASS"
    assert run([KID], {}).checks[0].action == "WARN"


# ------------------------------------------------------------------ wording
def test_needs_have_their_own_row_and_are_not_mixed_into_the_food_warnings():
    x = cand([PET, KID], {})
    assert attribute_warnings(x, NEED_ATTRS) == [] and declaration_statements(x, NEED_ATTRS) == []
    by = {n["code"]: n for n in need_items(x)}
    assert by["pets"]["status"] == "unknown" and "資訊不足" in by["pets"]["text"] and "先向店家確認" in by["pets"]["text"]
    assert by["kids"]["status"] == "unknown"


def test_a_declared_pet_policy_is_a_dated_fact_about_pets_not_a_menu_item():
    ok = cand([PET], {"pets_allowed": st("CONFIRMED_PRESENT", 1, declared=True, declared_on="2026-11-01", verified_on="2026-11-04")})
    [n] = need_items(ok)
    assert n["status"] == "yes" and n["text"] == "店家於 2026/11/01 聲明可攜帶寵物入內。已由揪呷人工驗證身分。"
    no = cand([KID], {"kid_friendly": st("CONFIRMED_ABSENT", 1, declared=True, declared_on="2026-11-01")})
    [k] = need_items(no)
    assert k["status"] == "no" and "沒有兒童座椅與兒童餐" in k["text"] and "不會排除這家店" in k["text"]
    maybe = cand([PET], {"pets_allowed": st("LIKELY_PRESENT", 1)})
    assert need_items(maybe)[0]["status"] == "maybe" and "未經店家確認" in need_items(maybe)[0]["text"]
    for item in (n, k, *need_items(maybe)):
        assert not any(w in item["text"] for w in FORBIDDEN_WORDS)


def test_no_group_need_means_no_need_rows():
    assert need_items(cand([], {})) == []


# ------------------------------------------------------------------ merchant form
def test_the_merchant_form_asks_about_pets_and_children_in_their_own_words():
    attrs = {c: {"attribute_type": a.attribute_type, "risk_level": a.risk_level} for c, a in NEED_ATTRS.items() if c in (
        "pets_allowed", "kid_friendly", "peanut")}
    sec = {s["key"]: s for s in form_spec(attrs)["sections"]}["needs"]
    pets = next(i for i in sec["items"] if i["attribute_code"] == "pets_allowed")
    assert "帶寵物入內用餐嗎" in pets["question"] and [a["label"] for a in pets["answers"]] == ["可以", "不可以", "我不確定"]
    assert "餐點" not in pets["question"] and pets["cross_contact"] is None


def test_the_merchant_preview_for_pets_and_children_is_a_dated_statement():
    row = dict(attribute_code="pets_allowed", attribute_type="require", new_state="CONFIRMED_ABSENT", cross_contact_status="unknown",
               capped_by_cross_contact=False, presence_extent=None)
    out = describe(row, "2026-11-08")
    assert out["text"] == "店家於 2026-11-08 聲明不可攜帶寵物入內。" and out["effect"] == "confirmed"
    kid = describe({**row, "attribute_code": "kid_friendly", "new_state": "LIKELY_PRESENT"}, "2026-11-08")
    assert kid["text"] == "店家於 2026-11-08 聲明提供兒童座椅或兒童餐（尚未達到「已確認」）。" and kid["effect"] == "possible"
