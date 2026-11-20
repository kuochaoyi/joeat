"""Recommendation orchestration: load pool + inputs from PostgreSQL -> run the pure engine -> persist EVERYTHING -> read back.

Every restaurant in the pool is stored as a recommendation_candidate (excluded ones too), together with one
recommendation_constraint_check row per (restaurant, participant, constraint) and the score components, so each decision
can be explained later. The API response is built from what was stored (one code path for POST and GET).
"""
from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import datetime, timezone

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppError, not_found
from app.core.ui_meta import GROUP_NEEDS
from app.db.session import apply_runtime_flags
from app.models.enrichment import RestaurantAttributeEvidence, RestaurantCuisine, RestaurantOpeningHours
from app.models.identity import Restaurant, RestaurantSourceEntity
from app.models.product import (
    DiningSession, Participant, ParticipantBudget, ParticipantHardConstraint, ParticipantPreference,
    RecommendationCandidate, RecommendationConstraintCheck, RecommendationRun, RecommendationScoreComponent,
)
from app.models.ref import Attribute, ConstraintDecisionRule, ConstraintReason, CuisineTag, ScoringConfig as ScoringConfigRow
from app.recommendation.engine import CandidateResult, EngineInput, EngineOutput, RestaurantInput, run_engine
from app.recommendation.explain import build_explanation
from app.recommendation.scoring import ScoringConfig
from app.recommendation.types import AttributeInfo, AttributeState, Constraint, Rule
from app.services import sessions as sess


# ---------------------------------------------------------------- loading
def load_rules(db: Session) -> dict:
    return {(r.attribute_type, r.risk_level, r.state): Rule(r.action, r.warning_level, r.may_show_safe_badge) for r in db.scalars(select(ConstraintDecisionRule))}


def load_attributes(db: Session) -> dict[str, AttributeInfo]:
    return {a.attribute_code: AttributeInfo(a.attribute_code, a.display_name_zh, a.attribute_type, a.risk_level, a.default_constraint_class)
            for a in db.scalars(select(Attribute))}


def load_config(db: Session) -> ScoringConfig:
    row = db.scalars(select(ScoringConfigRow).where(ScoringConfigRow.is_active)).first()
    if row is None:
        raise AppError(500, "no_scoring_config", "no active scoring config (run scripts/seed.py)")
    return ScoringConfig.from_json(row.version, row.config)


def _evidence_snapshots(db: Session, ids: set[int]) -> dict[int, dict]:
    if not ids:
        return {}
    rows = db.scalars(select(RestaurantAttributeEvidence).where(RestaurantAttributeEvidence.evidence_id.in_(ids))).all()
    declared = {d: day for d, day in db.execute(text(
        "SELECT declaration_id, ((attested_at AT TIME ZONE 'UTC') + interval '8 hours')::date FROM merchant.declaration WHERE declaration_id = ANY(:ids)"),
        {"ids": [e.declaration_id for e in rows if e.declaration_id is not None]})}
    return {e.evidence_id: {"declared_on": declared[e.declaration_id].isoformat() if e.declaration_id in declared else None,"text": e.evidence_text, "basis": e.evidence_basis, "applies_to": e.applies_to, "confidence": e.confidence,
                            "source_id": e.source_id, "source_url": e.source_url, "last_verified_at": e.last_verified_at.isoformat(),
                            "declaration_id": e.declaration_id, "presence_extent": e.presence_extent, "cross_contact_status": e.cross_contact_status} for e in rows}


def _state(raw, snaps: dict[int, dict]) -> AttributeState:
    snap = snaps.get(raw.deciding_evidence_id)
    if snap is None:
        return AttributeState(raw.state, raw.deciding_evidence_id, None)
    return AttributeState(raw.state, raw.deciding_evidence_id, snap, declared=snap["declaration_id"] is not None, presence_extent=snap["presence_extent"],
                          cross_contact=snap["cross_contact_status"], verified_on=snap["last_verified_at"][:10], declared_on=snap["declared_on"])


def load_engine_input(db: Session, session: DiningSession) -> tuple[EngineInput, list[Participant]]:
    people = db.scalars(select(Participant).where(Participant.session_id == session.session_id).order_by(Participant.participant_id)).all()
    pids = [p.participant_id for p in people]
    attributes = load_attributes(db)
    reasons = db.scalars(select(ConstraintReason)).all()
    reason_risk = {r.reason: r.min_risk_level for r in reasons}
    reason_class = {r.reason: r.constraint_class for r in reasons}
    strict = {p.participant_id for p in people if p.strict_allergy}

    cons = db.scalars(select(ParticipantHardConstraint).where(ParticipantHardConstraint.participant_id.in_(pids))).all() if pids else []
    constraints = [Constraint(str(x.participant_id), x.attribute_code, x.reason, x.participant_id in strict) for x in cons]
    if pids:
        rep = str(min(pids))                      # the needs are the GROUP's, shown without any name; they just need a participant row to hang the stored checks on
        constraints += [Constraint(rep, code, "unspecified", False, soft) for flag, (code, soft) in GROUP_NEEDS.items() if getattr(session, flag)]
    prefs: dict[str, dict[str, str]] = {str(p.participant_id): {} for p in people}      # everyone counts, even without preferences
    for x in (db.scalars(select(ParticipantPreference).where(ParticipantPreference.participant_id.in_(pids))).all() if pids else []):
        prefs[str(x.participant_id)][x.cuisine_tag] = x.stance
    any_budget = bool(pids) and db.scalar(select(func.count()).select_from(ParticipantBudget).where(ParticipantBudget.participant_id.in_(pids))) > 0

    pool = db.scalars(select(Restaurant).where(
        Restaurant.pool_status == "in_pool", Restaurant.active_status.in_(("active", "unverified")),
        Restaurant.merged_into_restaurant_id.is_(None), Restaurant.district == session.area).order_by(Restaurant.restaurant_id)).all()
    rids = [r.restaurant_id for r in pool]

    apply_runtime_flags(db)                                                              # test-fixture evidence stays hidden unless enabled
    codes = sorted({c.attribute_code for c in constraints})
    states_raw = db.execute(text(
        "SELECT restaurant_id, attribute_code, state::text AS state, deciding_evidence_id FROM enrichment.restaurant_attribute_state "
        "WHERE attribute_code = ANY(:codes) AND restaurant_id = ANY(:rids)"), {"codes": codes, "rids": rids}).all() if codes and rids else []
    snaps = _evidence_snapshots(db, {r.deciding_evidence_id for r in states_raw if r.deciding_evidence_id})
    states: dict[uuid.UUID, dict[str, AttributeState]] = defaultdict(dict)
    for r in states_raw:
        states[r.restaurant_id][r.attribute_code] = _state(r, snaps)

    cuisine: dict[uuid.UUID, list[tuple[str, str | None]]] = defaultdict(list)
    for rc, ct in db.execute(select(RestaurantCuisine, CuisineTag).join(CuisineTag, CuisineTag.tag == RestaurantCuisine.tag).where(RestaurantCuisine.restaurant_id.in_(rids))):
        pair = (rc.tag, ct.parent_tag)
        if pair not in cuisine[rc.restaurant_id]:
            cuisine[rc.restaurant_id].append(pair)
    settled = dict(db.execute(select(RestaurantSourceEntity.restaurant_id, func.count(func.distinct(RestaurantSourceEntity.source_id)))
                              .where(RestaurantSourceEntity.restaurant_id.in_(rids), RestaurantSourceEntity.match_status.in_(("auto", "manual_confirmed")))
                              .group_by(RestaurantSourceEntity.restaurant_id)).all())
    hours: dict[uuid.UUID, str] = {}
    for rid, consistencies in db.execute(select(RestaurantOpeningHours.restaurant_id, func.array_agg(RestaurantOpeningHours.consistency)).where(RestaurantOpeningHours.restaurant_id.in_(rids)).group_by(RestaurantOpeningHours.restaurant_id)):
        hours[rid] = "conflict" if "conflict" in consistencies else "ok"

    restaurants = [RestaurantInput(
        restaurant_id=str(r.restaurant_id), name=r.canonical_name, lat=r.lat, lon=r.lon, cuisine_tags=cuisine.get(r.restaurant_id, []),
        states=states.get(r.restaurant_id, {}), settled_source_count=settled.get(r.restaurant_id, 0), hours_status=hours.get(r.restaurant_id, "none"),
        active_status=r.active_status) for r in pool]
    inp = EngineInput(restaurants=restaurants, constraints=constraints, preferences=prefs, attributes=attributes, reason_min_risk=reason_risk,
                      rules=load_rules(db), reason_class=reason_class, config=load_config(db), meeting_lat=session.meeting_lat, meeting_lon=session.meeting_lon, any_budget=any_budget)
    return inp, list(people)


# ---------------------------------------------------------------- persisting
def persist(db: Session, session: DiningSession, inp: EngineInput, out: EngineOutput) -> uuid.UUID:
    run_id = uuid.uuid4()
    now = datetime.now(timezone.utc)
    db.add(RecommendationRun(run_id=run_id, session_id=session.session_id, scoring_version=inp.config.version,
                            config_snapshot={**inp.config.raw, "run_options": {"strict_mode": any(c.strict for c in inp.constraints)}},
                             data_snapshot_at=now, pool_size=len(out.candidates), excluded_count=len(out.excluded), eligible_count=len(out.eligible), completed_at=now))
    db.flush()
    comp_rows: list[RecommendationScoreComponent] = []
    check_rows: list[RecommendationConstraintCheck] = []
    for c in out.candidates:
        rid = uuid.UUID(c.restaurant.restaurant_id)
        if c.stage == "excluded":
            explanation = {"exclusion_reasons": c.filter.exclusion_reasons}
            row = RecommendationCandidate(run_id=run_id, restaurant_id=rid, stage="excluded", explanation=explanation, warnings=[])
        else:
            s = c.score
            row = RecommendationCandidate(
                run_id=run_id, restaurant_id=rid, stage=c.stage, distance_m=s.distance_m, cuisine_score=s.cuisine_score, distance_score=s.distance_score,
                data_confidence_score=s.data_confidence_score, rating_score=None, total_score=s.total_score, rank=c.rank, warning_count=c.warning_count,
                critical_warning_count=c.critical_warning_count, warnings=c.warnings, explanation=build_explanation(c, inp.preferences, inp.attributes))
            for comp in s.components:
                comp_rows.append(RecommendationScoreComponent(
                    run_id=run_id, session_id=session.session_id, restaurant_id=rid, component=comp.component,
                    participant_id=uuid.UUID(comp.participant_id) if comp.participant_id else None, raw_value=comp.raw_value, points=comp.points, detail=comp.detail))
        db.add(row)
        for k in c.filter.checks:
            check_rows.append(RecommendationConstraintCheck(
                run_id=run_id, session_id=session.session_id, restaurant_id=rid, participant_id=uuid.UUID(k.participant_id), attribute_code=k.attribute_code,
                attribute_type=k.attribute_type, effective_risk_level=k.effective_risk_level, evidence_state=k.evidence_state, action=k.action,
                warning_level=k.warning_level, may_show_safe_badge=k.may_show_safe_badge, deciding_evidence_id=k.deciding_evidence_id,
                evidence_snapshot=dict(k.evidence_snapshot) if k.evidence_snapshot else None, message_zh=k.message_zh))
    db.flush()
    db.add_all(comp_rows)
    db.add_all(check_rows)
    session.status = "recommended"
    db.commit()
    return run_id


def run_recommendation(db: Session, session_id: uuid.UUID, allow_partial: bool = False, include_excluded: bool = False) -> dict:
    session = sess.get_open_session(db, session_id)
    prog = sess.progress(db, session)
    if prog["joined"] < 1:
        raise AppError(409, "no_participants", "nobody has joined this session yet")
    if not prog["ready_for_recommendation"] and not allow_partial:
        raise AppError(409, "incomplete", "some participants have not finished; retry with allow_partial=true to run anyway",
                       {"missing_count": prog["missing_count"], "joined": prog["joined"], "all_complete": prog["all_complete"]})
    inp, _ = load_engine_input(db, session)
    out = run_engine(inp)
    run_id = persist(db, session, inp, out)
    return build_response(db, session, run_id, include_excluded)


# ---------------------------------------------------------------- reading
def latest_run_id(db: Session, session_id: uuid.UUID) -> uuid.UUID:
    rid = db.scalar(select(RecommendationRun.run_id).where(RecommendationRun.session_id == session_id, RecommendationRun.completed_at.is_not(None))
                    .order_by(RecommendationRun.created_at.desc()).limit(1))
    if rid is None:
        raise not_found("recommendation (none generated yet)")
    return rid


def get_recommendation(db: Session, session_id: uuid.UUID, include_excluded: bool = False) -> dict:
    session = sess.get_session(db, session_id)
    return build_response(db, session, latest_run_id(db, session_id), include_excluded)


def build_response(db: Session, session: DiningSession, run_id: uuid.UUID, include_excluded: bool) -> dict:
    run = db.get(RecommendationRun, run_id)
    tops = db.execute(select(RecommendationCandidate, Restaurant).join(Restaurant, Restaurant.restaurant_id == RecommendationCandidate.restaurant_id)
                      .where(RecommendationCandidate.run_id == run_id, RecommendationCandidate.stage == "top3").order_by(RecommendationCandidate.rank)).all()
    cuisines: dict[uuid.UUID, list[str]] = defaultdict(list)
    for rid, tag in db.execute(select(RestaurantCuisine.restaurant_id, RestaurantCuisine.tag).where(RestaurantCuisine.restaurant_id.in_([r.restaurant_id for _, r in tops]))):
        if tag not in cuisines[rid]:
            cuisines[rid].append(tag)
    items = []
    for cand, r in tops:
        ex = cand.explanation or {}
        warnings = [{"code": w["code"], "level": w["level"], "text": w["text"], "attribute": w["attribute"], "display": w["display"]} for w in ex.get("attribute_warnings", [])]
        warnings += [{"code": n["code"], "level": n["level"], "text": n["text"]} for n in ex.get("notes", [])]
        items.append({
            "rank": cand.rank, "restaurant_id": r.restaurant_id, "name": r.canonical_name, "address": r.canonical_address, "phone": r.phone,
            "cuisines": cuisines.get(r.restaurant_id, []), "distance_m": cand.distance_m,
            "score": {"cuisine": float(cand.cuisine_score), "distance": float(cand.distance_score), "data_confidence": float(cand.data_confidence_score),
                      "rating": None if cand.rating_score is None else float(cand.rating_score), "total": float(cand.total_score)},
            "hard_constraint": ex.get("hard_constraint", {"status": "no_constraints", "unknown_attributes": [], "confirmed_safe": [], "note": ""}),
            "warnings": warnings, "reasons": [x["text"] for x in ex.get("reasons", [])], "summary": ex.get("summary_zh", ""),
            "declarations": ex.get("declarations", []), "needs": ex.get("needs", []),
        })
    excluded = None
    if include_excluded:
        rows = db.execute(select(RecommendationCandidate.restaurant_id, Restaurant.canonical_name).join(Restaurant, Restaurant.restaurant_id == RecommendationCandidate.restaurant_id)
                          .where(RecommendationCandidate.run_id == run_id, RecommendationCandidate.stage == "excluded").order_by(Restaurant.canonical_name)).all()
        why: dict[uuid.UUID, set[str]] = defaultdict(set)
        for rid, msg in db.execute(select(RecommendationConstraintCheck.restaurant_id, RecommendationConstraintCheck.message_zh)
                                   .where(RecommendationConstraintCheck.run_id == run_id, RecommendationConstraintCheck.action == "EXCLUDE")):
            why[rid].add(msg)
        excluded = [{"restaurant_id": rid, "name": name, "reasons": sorted(why[rid])} for rid, name in rows]
    return {
        "run_id": run.run_id, "session_id": session.session_id, "created_at": run.created_at, "scoring_version": run.scoring_version,
        "participants": sess.participant_count(db, session.session_id), "party_size": session.party_size, "pool_size": run.pool_size,
        "excluded_count": run.excluded_count, "eligible_count": run.eligible_count, "top3": items, "excluded": excluded,
        "test_evidence_enabled": get_settings().allow_test_evidence,
        "strict_mode": bool((run.config_snapshot or {}).get("run_options", {}).get("strict_mode")),
    }
