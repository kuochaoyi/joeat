"""Hard Constraint filter.

Input : each participant's constraints + a restaurant's attribute states (evidence-based) + the decision rule book.
Output: per restaurant -> eligible?, exclusion_reasons[], unknown_warnings[], warnings[] (+ the full per-participant checks for auditing).

Principles (see recommendation_data_contract.md):
  * UNKNOWN is never safe. It does not exclude, but it always produces a warning.
  * LIKELY_ABSENT is treated like UNKNOWN. Only a first-party CONFIRMED_ABSENT may be shown as a positive safe signal.
  * One participant's EXCLUDE excludes the restaurant for the whole group.
"""
from __future__ import annotations

from typing import Iterable, Mapping

from app.recommendation.types import (
    RISK_RANK, AttributeInfo, AttributeState, CheckResult, Constraint, FilterResult, RuleBook,
)


def effective_risk(attribute_risk: str, reason_min_risk: str) -> str:
    """A participant's reason (allergy, religion...) can raise the risk level, never lower it."""
    return reason_min_risk if RISK_RANK[reason_min_risk] > RISK_RANK[attribute_risk] else attribute_risk


def effective_class(reason: str, attr: AttributeInfo, reason_class: Mapping[str, str]) -> str:
    """safety | preference. The member's own reason decides; without one the attribute's default does (allergens -> safety)."""
    if reason == "unspecified" or reason not in reason_class:
        return attr.default_class
    return reason_class[reason]


def _message(attr: AttributeInfo, action: str, state: str, safe_badge: bool, note: str | None = None) -> str:
    name = attr.display_name_zh
    if note == "softened_some":
        return f"{name}：店家表示有些餐點含有，可選擇不含的餐點，請向店家確認"
    if note == "strict_allergy":
        return f"{name}：沒有店家確認"
    if note == "soft_need":
        return f"{name}：店家表示沒有，請自行考量"
    if action == "EXCLUDE" and attr.code == "pets_allowed":
        return f"{name}：店家表示不可攜帶寵物入內"
    if action == "EXCLUDE":
        return f"{name}：此店{'含有/疑似含有' if attr.attribute_type == 'avoid' else '不符合'}"
    if action == "PASS":
        return f"{name}：{'已有第一手資料確認符合' if safe_badge else '符合'}"
    if action == "PASS_CONDITIONAL":
        return f"{name}：可能符合，但未經店家確認"
    return f"{name}：資料不足，無法確認，請向店家確認"


def evaluate_restaurant(
    restaurant_id: str,
    constraints: Iterable[Constraint],
    attributes: Mapping[str, AttributeInfo],
    reason_min_risk: Mapping[str, str],
    states: Mapping[str, AttributeState],
    rules: RuleBook,
    reason_class: Mapping[str, str] | None = None,
) -> FilterResult:
    """Looks up the rule matrix, then applies the two member-level adjustments (docs/decisions/0001-merchant-declaration.md):

    * softened_some - a PREFERENCE constraint ("don't eat beef") on a non-critical attribute: when the restaurant declared that only SOME dishes
      contain it, EXCLUDE becomes a high warning ("choose a dish without it"). Most / unknown extent, safety constraints and critical
      attributes keep the matrix result.
    * strict_allergy - the member opted in: a SAFETY constraint ("avoid" type) is only passed on a confirmed absence, so UNKNOWN / LIKELY_ABSENT
      (including "declared absent but shared equipment possible / unknown") excludes the restaurant.
    * soft_need - a group need that may only warn (bringing a child): an explicit refusal becomes a normal warning instead of an exclusion.
    """
    reason_class = reason_class or {}
    result = FilterResult(restaurant_id=restaurant_id)
    for c in constraints:
        attr = attributes[c.attribute_code]
        st = states.get(c.attribute_code) or AttributeState()     # no evidence at all == UNKNOWN
        risk = effective_risk(attr.risk_level, reason_min_risk.get(c.reason, "normal"))
        rule = rules[(attr.attribute_type, risk, st.state)]
        cclass = effective_class(c.reason, attr, reason_class)
        action, level, note = rule.action, rule.warning_level, None
        if (action == "EXCLUDE" and attr.attribute_type == "avoid" and cclass == "preference" and attr.risk_level != "critical"
                and st.presence_extent == "some" and st.state in ("CONFIRMED_PRESENT", "LIKELY_PRESENT")):
            action, level, note = "WARN", "high", "softened_some"
        elif c.strict and cclass == "safety" and attr.attribute_type == "avoid" and action == "WARN" and st.state in ("UNKNOWN", "LIKELY_ABSENT"):
            action, level, note = "EXCLUDE", "none", "strict_allergy"
        elif c.soft and action == "EXCLUDE":
            action, level, note = "WARN", "normal", "soft_need"
        snapshot = st.evidence_snapshot
        if note:
            snapshot = {**(snapshot or {}), "engine_note": note}
        result.checks.append(
            CheckResult(
                participant_id=c.participant_id, attribute_code=c.attribute_code, attribute_type=attr.attribute_type,
                effective_risk_level=risk, evidence_state=st.state, action=action, warning_level=level,
                may_show_safe_badge=rule.may_show_safe_badge, deciding_evidence_id=st.deciding_evidence_id,
                evidence_snapshot=snapshot, message_zh=_message(attr, action, st.state, rule.may_show_safe_badge, note),
                constraint_class=cclass, engine_note=note, declared=st.declared, presence_extent=st.presence_extent,
                cross_contact=st.cross_contact, verified_on=st.verified_on, declared_on=st.declared_on,
            )
        )
    return result


def filter_restaurants(
    states_by_restaurant: Mapping[str, Mapping[str, AttributeState]],
    constraints: list[Constraint],
    attributes: Mapping[str, AttributeInfo],
    reason_min_risk: Mapping[str, str],
    rules: RuleBook,
    reason_class: Mapping[str, str] | None = None,
) -> tuple[list[FilterResult], list[FilterResult]]:
    """Returns (eligible, excluded). Restaurants without any recorded state are evaluated as all-UNKNOWN."""
    eligible: list[FilterResult] = []
    excluded: list[FilterResult] = []
    for rid, states in states_by_restaurant.items():
        res = evaluate_restaurant(rid, constraints, attributes, reason_min_risk, states, rules, reason_class)
        (eligible if res.eligible else excluded).append(res)
    return eligible, excluded
