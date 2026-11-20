"""Dining sessions, participants and what they submit (hard constraints, soft preferences)."""
from __future__ import annotations

import uuid
from datetime import date, datetime, time, timedelta, timezone

import httpx
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppError, not_found
from app.core.security import hash_ref
from app.core.ui_meta import ALLERGEN_CODES, LOCATION_PRESETS
from app.models.product import (
    DiningSession, Participant, ParticipantBudget, ParticipantHardConstraint, ParticipantPreference, TimeOption,
)
from app.models.ref import Attribute, ConstraintReason, CuisineTag
from app.schemas.api import ConstraintsSubmit, ParticipantCreate, PreferencesSubmit, SessionCreate

TAIPEI = timezone(timedelta(hours=8))
MAX_PARTICIPANTS = 20
# 鹽埕區 is the only area with restaurant data: a meeting point farther than this from its centre still works but every restaurant is "far"
COVERAGE_CENTER = (22.6245, 120.2815)
COVERAGE_RADIUS_M = 3000
TAIWAN_BOX = (21.5, 25.6, 119.0, 122.2)          # lat_min, lat_max, lon_min, lon_max


def now() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------- sessions
def create_session(db: Session, data: SessionCreate) -> DiningSession:
    lat, lon, label = data.meeting_lat, data.meeting_lon, data.location_label
    if data.location_preset:
        preset = next((p for p in LOCATION_PRESETS if p["key"] == data.location_preset), None)
        if preset is None:
            raise AppError(422, "unknown_location_preset", f"unknown location preset {data.location_preset}")
        lat, lon, label = preset["lat"], preset["lon"], label or preset["label"]
    if (lat is None) != (lon is None):
        raise AppError(422, "bad_coordinates", "meeting_lat and meeting_lon must be given together")
    if lat is not None and not (TAIWAN_BOX[0] <= lat <= TAIWAN_BOX[1] and TAIWAN_BOX[2] <= lon <= TAIWAN_BOX[3]):
        raise AppError(422, "outside_taiwan", "the meeting point must be in Taiwan")
    meal_time = None
    if data.date and data.time_mode == "fixed":
        meal_time = datetime.combine(data.date, data.time or time(18, 0), tzinfo=TAIPEI)
    slots: list[datetime] = []
    if data.time_mode == "poll":
        slots = sorted({(s if s.tzinfo else s.replace(tzinfo=TAIPEI)).astimezone(timezone.utc) for s in data.time_slots})
        if len(slots) < 2:
            raise AppError(422, "poll_needs_options", "a time poll needs at least 2 different time slots")
        if slots[0] < now() - timedelta(hours=1):
            raise AppError(422, "slot_in_the_past", "time slots must be in the future")
    elif data.time_slots:
        raise AppError(422, "slots_need_poll", "time_slots only apply when time_mode is 'poll'")
    host_ref = None
    if data.host_line_user_id:
        host_ref = hash_ref(resolve_line_user(ParticipantCreate(line_user_id=data.host_line_user_id, id_token=data.host_id_token)))
    s = DiningSession(
        title=data.title.strip(), location_label=label, meeting_lat=lat, meeting_lon=lon, meal_time=meal_time,
        party_size=data.party_size, radius_m=1500,
        line_group_ref=hash_ref(data.line_group_id) if data.line_group_id else None,
        host_ref=host_ref, time_mode=data.time_mode, needs_pets=data.needs_pets, needs_kids=data.needs_kids,
        time_deadline=now() + timedelta(hours=data.time_deadline_hours or 24) if data.time_mode == "poll" else None,
    )
    db.add(s)
    db.flush()
    for st in slots:
        db.add(TimeOption(session_id=s.session_id, starts_at=st))
    db.commit()
    return s


def outside_coverage(s: DiningSession) -> bool:
    if s.meeting_lat is None or s.meeting_lon is None:
        return False
    from app.recommendation.scoring import distance_m
    d = distance_m(s.meeting_lat, s.meeting_lon, COVERAGE_CENTER[0], COVERAGE_CENTER[1])
    return d is not None and d > COVERAGE_RADIUS_M


def is_host(s: DiningSession, p: Participant) -> bool:
    """No host (bot-created session) = nobody has host powers; callers decide whether that means 'anyone'."""
    return s.host_ref is not None and p.line_user_ref == s.host_ref


def get_session(db: Session, session_id: uuid.UUID) -> DiningSession:
    s = db.get(DiningSession, session_id)
    if s is None:
        raise not_found("session")
    return s


def get_open_session(db: Session, session_id: uuid.UUID) -> DiningSession:
    s = get_session(db, session_id)
    if s.expires_at <= now():
        raise AppError(410, "session_expired", "this dining session has expired")
    if s.status == "closed":
        raise AppError(409, "session_closed", "this dining session is closed")
    return s


def latest_session_for_group(db: Session, group_id: str) -> DiningSession | None:
    return db.scalars(
        select(DiningSession)
        .where(DiningSession.line_group_ref == hash_ref(group_id), DiningSession.status != "closed", DiningSession.expires_at > func.now())
        .order_by(DiningSession.created_at.desc()).limit(1)
    ).first()


def participant_count(db: Session, session_id: uuid.UUID) -> int:
    return db.scalar(select(func.count()).select_from(Participant).where(Participant.session_id == session_id)) or 0


# ---------------------------------------------------------------- participants
def resolve_line_user(data: ParticipantCreate) -> str:
    """Dev mode trusts the client-supplied id. In 'line' mode the LIFF ID token is verified with LINE and its `sub` is used."""
    settings = get_settings()
    if settings.auth_mode != "line":
        return data.line_user_id
    if not data.id_token or not settings.line_channel_id:
        raise AppError(401, "id_token_required", "a LIFF ID token is required")
    resp = httpx.post("https://api.line.me/oauth2/v2.1/verify", data={"id_token": data.id_token, "client_id": settings.line_channel_id}, timeout=10)
    if resp.status_code != 200 or "sub" not in resp.json():
        raise AppError(401, "invalid_id_token", "the LIFF ID token could not be verified")
    return resp.json()["sub"]


def add_participant(db: Session, session: DiningSession, data: ParticipantCreate) -> tuple[Participant, bool]:
    ref = hash_ref(resolve_line_user(data))
    existing = db.scalars(select(Participant).where(Participant.session_id == session.session_id, Participant.line_user_ref == ref)).first()
    if existing:
        return existing, False
    count = participant_count(db, session.session_id)
    limit = min(session.party_size or MAX_PARTICIPANTS, MAX_PARTICIPANTS)
    if count >= limit:
        raise AppError(409, "session_full", f"this session is limited to {limit} participants")
    p = Participant(session_id=session.session_id, line_user_ref=ref, label=(data.label or f"成員{count + 1}").strip())
    db.add(p)
    db.commit()
    return p, True


def get_participant(db: Session, participant_id: uuid.UUID) -> Participant:
    p = db.get(Participant, participant_id)
    if p is None:
        raise not_found("participant")
    return p


def _touch_submitted(p: Participant) -> None:
    if p.constraints_submitted_at and p.preferences_submitted_at and not p.submitted_at:
        p.submitted_at = now()


def submit_constraints(db: Session, p: Participant, data: ConstraintsSubmit) -> int:
    get_open_session(db, p.session_id)
    valid = {a.attribute_code for a in db.scalars(select(Attribute).where(Attribute.is_active))}
    reasons = {r.reason for r in db.scalars(select(ConstraintReason))}
    for it in data.items:
        if it.attribute_code not in valid:
            raise AppError(422, "unknown_attribute", f"unknown attribute {it.attribute_code}")
        if it.reason is not None and it.reason not in reasons:
            raise AppError(422, "unknown_reason", f"unknown reason {it.reason}")
    db.execute(delete(ParticipantHardConstraint).where(ParticipantHardConstraint.participant_id == p.participant_id))
    for it in data.items:
        reason = it.reason or ("allergy" if it.attribute_code in ALLERGEN_CODES else "unspecified")
        db.add(ParticipantHardConstraint(participant_id=p.participant_id, attribute_code=it.attribute_code, reason=reason))
    db.execute(delete(ParticipantBudget).where(ParticipantBudget.participant_id == p.participant_id))
    if data.budget_max_per_person:
        db.add(ParticipantBudget(participant_id=p.participant_id, max_per_person=data.budget_max_per_person))
    p.strict_allergy = bool(data.strict_allergy)
    p.constraints_submitted_at = now()
    _touch_submitted(p)
    db.commit()
    return len(data.items)


def submit_preferences(db: Session, p: Participant, data: PreferencesSubmit) -> int:
    get_open_session(db, p.session_id)
    valid = {t.tag for t in db.scalars(select(CuisineTag))}
    for it in data.items:
        if it.cuisine_tag not in valid:
            raise AppError(422, "unknown_cuisine", f"unknown cuisine tag {it.cuisine_tag}")
    db.execute(delete(ParticipantPreference).where(ParticipantPreference.participant_id == p.participant_id))
    for it in data.items:
        db.add(ParticipantPreference(participant_id=p.participant_id, cuisine_tag=it.cuisine_tag, stance=it.stance))
    p.preferences_submitted_at = now()
    _touch_submitted(p)
    db.commit()
    return len(data.items)


def get_answers(db: Session, p: Participant) -> dict:
    """What this participant has submitted, so the form can be re-opened and edited. The participant id is the capability: nobody else's answers are reachable."""
    cons = db.scalars(select(ParticipantHardConstraint).where(ParticipantHardConstraint.participant_id == p.participant_id).order_by(ParticipantHardConstraint.attribute_code)).all()
    prefs = db.scalars(select(ParticipantPreference).where(ParticipantPreference.participant_id == p.participant_id).order_by(ParticipantPreference.cuisine_tag)).all()
    budget = db.get(ParticipantBudget, p.participant_id)
    return {
        "constraints": [{"attribute_code": c.attribute_code, "reason": c.reason} for c in cons], "strict_allergy": bool(p.strict_allergy),
        "budget_max_per_person": budget.max_per_person if budget else None,
        "preferences": [{"cuisine_tag": x.cuisine_tag, "stance": x.stance} for x in prefs], "diet_type": p.diet_type,
        "constraints_submitted": p.constraints_submitted_at is not None, "preferences_submitted": p.preferences_submitted_at is not None,
    }


# ---------------------------------------------------------------- progress
def progress(db: Session, session: DiningSession, me: uuid.UUID | None = None) -> dict:
    people = db.scalars(select(Participant).where(Participant.session_id == session.session_id).order_by(Participant.label, Participant.participant_id)).all()
    rows = [{"label": x.label, "is_me": me is not None and x.participant_id == me, "constraints_done": x.constraints_submitted_at is not None,
             "preferences_done": x.preferences_submitted_at is not None} for x in people]
    complete = [r for r in rows if r["constraints_done"] and r["preferences_done"]]
    all_complete = bool(rows) and len(complete) == len(rows)
    expected = session.party_size or len(rows)
    return {
        "session_id": session.session_id, "party_size": session.party_size, "joined": len(rows),
        "constraints_done": sum(r["constraints_done"] for r in rows), "preferences_done": sum(r["preferences_done"] for r in rows),
        "participants": rows, "all_complete": all_complete,
        "ready_for_recommendation": all_complete and len(rows) >= 2,
        "missing_count": max(expected - len(complete), 0),
    }
