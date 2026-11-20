"""Builders for engine inputs, so unit tests read like scenarios."""
from __future__ import annotations

from app.recommendation.engine import RestaurantInput
from app.recommendation.rules import DEFAULT_RULES
from app.recommendation.types import AttributeInfo, AttributeState, Constraint

ATTRS = {
    "peanut": AttributeInfo("peanut", "花生", "avoid", "critical", "safety"),
    "beef": AttributeInfo("beef", "牛肉", "avoid", "high"),
    "pork": AttributeInfo("pork", "豬肉", "avoid", "high"),
    "seafood": AttributeInfo("seafood", "海鮮", "avoid", "high"),
    "offal": AttributeInfo("offal", "內臟", "avoid", "normal"),
    "vegetarian": AttributeInfo("vegetarian", "素食", "require", "high"),
    "gluten_free": AttributeInfo("gluten_free", "無麩質", "require", "critical", "safety"),
}
REASON_RISK = {"allergy": "critical", "medical": "critical", "religion": "high", "belief_diet": "high", "dislike": "normal", "unspecified": "normal"}
REASON_CLASS = {"allergy": "safety", "medical": "safety", "religion": "safety", "belief_diet": "preference", "dislike": "preference", "unspecified": "preference"}
RULES = DEFAULT_RULES


def st(state: str, evidence_id: int | None = None, **facts) -> AttributeState:
    """facts: declared / presence_extent / cross_contact / verified_on (what the merchant declaration said)."""
    return AttributeState(state=state, deciding_evidence_id=evidence_id, evidence_snapshot={"text": "test"} if evidence_id else None, **facts)


def restaurant(rid: str, name: str = "R", tags=(("台式", None),), states=None, lat=22.6242, lon=120.2841, settled=0, hours="ok", active="unverified"):
    return RestaurantInput(restaurant_id=rid, name=name, lat=lat, lon=lon, cuisine_tags=list(tags), states=states or {},
                           settled_source_count=settled, hours_status=hours, active_status=active)


def c(pid: str, attr: str, reason: str = "unspecified", strict: bool = False) -> Constraint:
    return Constraint(participant_id=pid, attribute_code=attr, reason=reason, strict=strict)
