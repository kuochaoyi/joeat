"""Recommendation engine: pure function from loaded inputs to ranked candidates. No I/O.

Pipeline: pool (already loaded) -> hard filter -> soft scoring (eligible only) -> sort -> Top N.
Excluded restaurants are NOT scored but are returned (and persisted by the service) so every decision can be explained.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping, Sequence

from app.recommendation.hard_filter import evaluate_restaurant
from app.recommendation.ranking import RankInput, rank
from app.recommendation.scoring import DEFAULT_CONFIG, ScoreBreakdown, ScoringConfig, distance_m, score_restaurant
from app.recommendation.types import AttributeInfo, AttributeState, Constraint, FilterResult, RuleBook


@dataclass
class RestaurantInput:
    restaurant_id: str
    name: str
    lat: float | None
    lon: float | None
    cuisine_tags: Sequence[tuple[str, str | None]]            # (tag, parent_tag)
    states: Mapping[str, AttributeState]                      # attribute_code -> effective state (missing = UNKNOWN)
    settled_source_count: int = 0                             # independent sources whose identity link is settled
    hours_status: str = "none"                                # none | conflict | ok
    active_status: str = "unverified"


@dataclass
class EngineInput:
    restaurants: Sequence[RestaurantInput]
    constraints: Sequence[Constraint]
    preferences: Mapping[str, Mapping[str, str]]              # participant_id -> {cuisine_tag: stance}
    attributes: Mapping[str, AttributeInfo]
    reason_min_risk: Mapping[str, str]
    rules: RuleBook
    reason_class: Mapping[str, str] = field(default_factory=dict)   # reason -> safety | preference
    config: ScoringConfig = DEFAULT_CONFIG
    meeting_lat: float | None = None
    meeting_lon: float | None = None
    any_budget: bool = False                                  # budget exists => "price information is insufficient" is shown


@dataclass
class CandidateResult:
    restaurant: RestaurantInput
    stage: str                                                # excluded | eligible | top3
    filter: FilterResult
    score: ScoreBreakdown | None = None
    warnings: list[dict] = field(default_factory=list)        # non-attribute notes (hours/price/distance)
    warning_count: int = 0
    critical_warning_count: int = 0
    rank: int | None = None


@dataclass
class EngineOutput:
    candidates: list[CandidateResult]

    @property
    def top(self) -> list[CandidateResult]:
        return sorted([c for c in self.candidates if c.stage == "top3"], key=lambda c: c.rank or 0)

    @property
    def excluded(self) -> list[CandidateResult]:
        return [c for c in self.candidates if c.stage == "excluded"]

    @property
    def eligible(self) -> list[CandidateResult]:
        return [c for c in self.candidates if c.stage != "excluded"]


def _non_attribute_warnings(r: RestaurantInput, dist: int | None, any_budget: bool) -> list[dict]:
    w: list[dict] = []
    if dist is None:
        w.append({"code": "distance_unknown", "level": "normal"})
    if r.hours_status == "none":
        w.append({"code": "hours_unknown", "level": "normal"})
    elif r.hours_status == "conflict":
        w.append({"code": "hours_conflict", "level": "normal"})
    if any_budget:
        w.append({"code": "price_unknown", "level": "normal"})
    return w


def run_engine(inp: EngineInput) -> EngineOutput:
    results: list[CandidateResult] = []
    for r in inp.restaurants:
        fres = evaluate_restaurant(r.restaurant_id, inp.constraints, inp.attributes, inp.reason_min_risk, r.states, inp.rules, inp.reason_class)
        dist = distance_m(inp.meeting_lat, inp.meeting_lon, r.lat, r.lon)
        if not fres.eligible:
            results.append(CandidateResult(restaurant=r, stage="excluded", filter=fres))
            continue
        score = score_restaurant(inp.preferences, r.cuisine_tags, dist, r.settled_source_count, inp.config)
        notes = _non_attribute_warnings(r, dist, inp.any_budget)
        wc = fres.warning_checks
        results.append(CandidateResult(
            restaurant=r, stage="eligible", filter=fres, score=score, warnings=notes,
            warning_count=len(wc) + len(notes), critical_warning_count=sum(1 for c in wc if c.warning_level == "critical"),
        ))
    eligible = [c for c in results if c.stage == "eligible"]
    ranked = rank([RankInput(c.restaurant.restaurant_id, c.score.total_score, c.critical_warning_count, c.warning_count, c.score.distance_m) for c in eligible],
                  inp.config.top_n)
    by_id = {c.restaurant.restaurant_id: c for c in eligible}
    for i, ri in enumerate(ranked, start=1):
        by_id[ri.restaurant_id].stage = "top3"
        by_id[ri.restaurant_id].rank = i
    return EngineOutput(candidates=results)
