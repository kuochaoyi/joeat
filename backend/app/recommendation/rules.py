"""Decision rule matrix (recommendation_data_contract.md section 4).

The authoritative copy lives in the database (ref.constraint_decision_rule, loaded by attribute_seed.sql) and is what
the API uses. DEFAULT_RULES is an in-code copy used by unit tests and as a fallback; an integration test asserts the two
are identical so they cannot drift.
"""
from app.recommendation.types import Rule, RuleBook

E, W, PC, P = "EXCLUDE", "WARN", "PASS_CONDITIONAL", "PASS"


def _rows() -> list[tuple[str, str, str, str, str, bool]]:
    rows: list[tuple[str, str, str, str, str, bool]] = []
    # avoid: user wants the thing NOT present
    rows += [("avoid", "critical", "CONFIRMED_PRESENT", E, "none", False), ("avoid", "critical", "LIKELY_PRESENT", E, "none", False),
             ("avoid", "critical", "UNKNOWN", W, "critical", False), ("avoid", "critical", "LIKELY_ABSENT", W, "critical", False),
             ("avoid", "critical", "CONFIRMED_ABSENT", P, "none", True)]
    rows += [("avoid", "high", "CONFIRMED_PRESENT", E, "none", False), ("avoid", "high", "LIKELY_PRESENT", E, "none", False),
             ("avoid", "high", "UNKNOWN", W, "high", False), ("avoid", "high", "LIKELY_ABSENT", W, "high", False),
             ("avoid", "high", "CONFIRMED_ABSENT", P, "none", True)]
    rows += [("avoid", "normal", "CONFIRMED_PRESENT", E, "none", False), ("avoid", "normal", "LIKELY_PRESENT", W, "high", False),
             ("avoid", "normal", "UNKNOWN", W, "normal", False), ("avoid", "normal", "LIKELY_ABSENT", W, "normal", False),
             ("avoid", "normal", "CONFIRMED_ABSENT", P, "none", True)]
    # require: user wants it present
    rows += [("require", "critical", "CONFIRMED_PRESENT", P, "none", True), ("require", "critical", "LIKELY_PRESENT", PC, "critical", False),
             ("require", "critical", "UNKNOWN", W, "critical", False), ("require", "critical", "LIKELY_ABSENT", E, "none", False),
             ("require", "critical", "CONFIRMED_ABSENT", E, "none", False)]
    rows += [("require", "high", "CONFIRMED_PRESENT", P, "none", True), ("require", "high", "LIKELY_PRESENT", PC, "normal", False),
             ("require", "high", "UNKNOWN", W, "high", False), ("require", "high", "LIKELY_ABSENT", E, "none", False),
             ("require", "high", "CONFIRMED_ABSENT", E, "none", False)]
    rows += [("require", "normal", "CONFIRMED_PRESENT", P, "none", True), ("require", "normal", "LIKELY_PRESENT", PC, "normal", False),
             ("require", "normal", "UNKNOWN", W, "normal", False), ("require", "normal", "LIKELY_ABSENT", W, "normal", False),
             ("require", "normal", "CONFIRMED_ABSENT", E, "none", False)]
    return rows


DEFAULT_RULES: RuleBook = {(t, r, s): Rule(a, w, safe) for t, r, s, a, w, safe in _rows()}
assert len(DEFAULT_RULES) == 30
