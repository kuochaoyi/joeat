"""Plain data types shared by the recommendation engine. No database or web imports here."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

RISK_RANK = {"critical": 3, "high": 2, "normal": 1}
EVIDENCE_STATES = ("CONFIRMED_PRESENT", "LIKELY_PRESENT", "LIKELY_ABSENT", "CONFIRMED_ABSENT", "UNKNOWN")
UNKNOWN_LIKE = ("UNKNOWN", "LIKELY_ABSENT")          # LIKELY_ABSENT is never "safe": it is treated like UNKNOWN


@dataclass(frozen=True)
class Rule:
    action: str                 # PASS | PASS_CONDITIONAL | WARN | EXCLUDE
    warning_level: str          # none | normal | high | critical
    may_show_safe_badge: bool = False


# (attribute_type, effective_risk_level, evidence_state) -> Rule
RuleBook = Mapping[tuple[str, str, str], Rule]


@dataclass(frozen=True)
class AttributeInfo:
    code: str
    display_name_zh: str
    attribute_type: str         # avoid | require
    risk_level: str             # critical | high | normal
    default_class: str = "preference"   # safety | preference: used when the member gave no reason


@dataclass(frozen=True)
class Constraint:
    participant_id: str
    attribute_code: str
    reason: str = "unspecified"
    strict: bool = False        # the member opted in to strict allergy mode (applies to their safety-class "avoid" constraints)
    soft: bool = False          # a group need that may only warn: an explicit refusal (EXCLUDE) is turned into a normal warning


@dataclass(frozen=True)
class AttributeState:
    state: str = "UNKNOWN"
    deciding_evidence_id: int | None = None
    evidence_snapshot: Mapping[str, Any] | None = None
    # facts about the deciding evidence (None for evidence that is not a merchant declaration)
    declared: bool = False                  # the deciding evidence is a merchant declaration
    presence_extent: str | None = None      # some | most (declared "present")
    cross_contact: str | None = None        # confirmed_none | possible | confirmed_shared | unknown (declared "absent" of a critical allergen)
    verified_on: str | None = None          # ISO date the evidence was last verified (the day a reviewer published it)
    declared_on: str | None = None          # ISO date the MERCHANT made the declaration: the date customers are shown


@dataclass
class CheckResult:
    participant_id: str
    attribute_code: str
    attribute_type: str
    effective_risk_level: str
    evidence_state: str
    action: str
    warning_level: str
    may_show_safe_badge: bool
    deciding_evidence_id: int | None
    evidence_snapshot: Mapping[str, Any] | None
    message_zh: str
    constraint_class: str = "preference"    # safety | preference (effective: reason first, attribute default otherwise)
    engine_note: str | None = None          # softened_some (EXCLUDE -> WARN: preference constraint, "some dishes") | strict_allergy (WARN -> EXCLUDE)
    declared: bool = False
    presence_extent: str | None = None
    cross_contact: str | None = None
    verified_on: str | None = None
    declared_on: str | None = None


@dataclass
class FilterResult:
    restaurant_id: str
    checks: list[CheckResult] = field(default_factory=list)

    @property
    def eligible(self) -> bool:
        return not any(c.action == "EXCLUDE" for c in self.checks)

    @property
    def exclusion_reasons(self) -> list[dict]:
        return [
            {"attribute": c.attribute_code, "reason": c.evidence_state, "risk_level": c.effective_risk_level, "message": c.message_zh}
            for c in self.checks if c.action == "EXCLUDE"
        ]

    @property
    def warning_checks(self) -> list[CheckResult]:
        return [c for c in self.checks if c.action in ("WARN", "PASS_CONDITIONAL")]

    @property
    def unknown_warnings(self) -> list[dict]:
        """Attributes nobody could confirm (UNKNOWN / LIKELY_ABSENT). Never reported as safe."""
        return [
            {"attribute": c.attribute_code, "reason": c.evidence_state, "level": c.warning_level, "message": c.message_zh}
            for c in self.checks if c.action == "WARN" and c.evidence_state in ("UNKNOWN", "LIKELY_ABSENT")
        ]

    @property
    def warnings(self) -> list[dict]:
        return [
            {"attribute": c.attribute_code, "reason": c.evidence_state, "level": c.warning_level, "message": c.message_zh}
            for c in self.warning_checks
        ]

    def to_dict(self) -> dict:
        """Shape requested for the hard-filter output. Participant ids are deliberately absent (privacy)."""
        return {
            "restaurant_id": self.restaurant_id,
            "eligible": self.eligible,
            "exclusion_reasons": self.exclusion_reasons,
            "unknown_warnings": self.unknown_warnings,
            "warnings": self.warnings,
        }
