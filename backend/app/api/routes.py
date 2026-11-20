"""REST API (see API.md). Group-level responses only: nobody's individual constraints are exposed."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core import diet_type
from app.core.errors import AppError
from app.models.product import Participant
from app.core.ui_meta import ATTRIBUTE_GROUPS, CUISINE_CHIPS, LOCATION_PRESETS, STANCES
from app.models.ref import Attribute, ConstraintReason
from app.schemas.api import (
    ConstraintsSubmit, ParticipantCreate, ParticipantOut, PreferencesSubmit, ProgressOut, RecommendationOut, RecommendationRequest,
    DietTypeIn, ReportIn, RestaurantDetail, SessionCreate, SessionOut,
)
from app.services import recommendations as rec
from app.services import reports
from app.services import time_polls
from app.services import restaurants as rest
from app.services import sessions as sess

router = APIRouter()


def _session_out(db: Session, s) -> SessionOut:
    time_polls.close_if_due(db, s)
    return SessionOut(session_id=s.session_id, title=s.title, area=s.area, location_label=s.location_label, meeting_lat=s.meeting_lat, meeting_lon=s.meeting_lon,
                      meal_time=s.meal_time, party_size=s.party_size, status=s.status, participant_count=sess.participant_count(db, s.session_id), expires_at=s.expires_at,
                      time_mode=s.time_mode, time_deadline=s.time_deadline, time_closed=s.time_closed_at is not None, outside_coverage=sess.outside_coverage(s),
                      needs_pets=s.needs_pets, needs_kids=s.needs_kids)


def _participant_out(db: Session, p) -> ParticipantOut:
    return ParticipantOut(participant_id=p.participant_id, session_id=p.session_id, label=p.label,
                          constraints_submitted=p.constraints_submitted_at is not None, preferences_submitted=p.preferences_submitted_at is not None,
                          is_host=sess.is_host(sess.get_session(db, p.session_id), p))


# ------------------------------------------------------------------ sessions
@router.post("/sessions", response_model=SessionOut, status_code=201)
def create_session(body: SessionCreate, db: Session = Depends(get_db)):
    return _session_out(db, sess.create_session(db, body))


@router.get("/sessions/{session_id}", response_model=SessionOut)
def get_session(session_id: uuid.UUID, db: Session = Depends(get_db)):
    return _session_out(db, sess.get_session(db, session_id))


@router.post("/sessions/{session_id}/participants", response_model=ParticipantOut, status_code=201)
def join_session(session_id: uuid.UUID, body: ParticipantCreate, db: Session = Depends(get_db)):
    """Idempotent: the same LINE user joining twice gets the same participant back."""
    s = sess.get_open_session(db, session_id)
    p, _created = sess.add_participant(db, s, body)
    return _participant_out(db, p)


@router.get("/sessions/{session_id}/progress", response_model=ProgressOut)
def get_progress(session_id: uuid.UUID, participant_id: uuid.UUID | None = Query(None, description="optional: marks that participant as is_me"), db: Session = Depends(get_db)):
    """Counts and done/not-done flags only: never anybody's constraints, and never other participants' ids."""
    return sess.progress(db, sess.get_session(db, session_id), me=participant_id)


# ------------------------------------------------------------------ participants
@router.get("/participants/{participant_id}", response_model=ParticipantOut)
def get_participant(participant_id: uuid.UUID, db: Session = Depends(get_db)):
    return _participant_out(db, sess.get_participant(db, participant_id))


@router.get("/participants/{participant_id}/answers")
def get_answers(participant_id: uuid.UUID, db: Session = Depends(get_db)):
    """This participant's own saved constraints / budget / preferences (so the forms can be re-opened and edited). The participant id is the capability."""
    return sess.get_answers(db, sess.get_participant(db, participant_id))


@router.post("/participants/{participant_id}/constraints")
def submit_constraints(participant_id: uuid.UUID, body: ConstraintsSubmit, db: Session = Depends(get_db)):
    """Replaces this participant's hard constraints. An empty list is valid ("nothing to declare") and marks the step as done."""
    p = sess.get_participant(db, participant_id)
    n = sess.submit_constraints(db, p, body)
    return {"saved": n, "participant": _participant_out(db, p)}


@router.post("/participants/{participant_id}/preferences")
def submit_preferences(participant_id: uuid.UUID, body: PreferencesSubmit, db: Session = Depends(get_db)):
    p = sess.get_participant(db, participant_id)
    n = sess.submit_preferences(db, p, body)
    return {"saved": n, "participant": _participant_out(db, p)}


# ------------------------------------------------------------------ recommendations
@router.post("/sessions/{session_id}/recommendations", response_model=RecommendationOut, status_code=201, response_model_exclude_none=False)
def create_recommendation(session_id: uuid.UUID, body: RecommendationRequest | None = None, include_excluded: bool = Query(False), db: Session = Depends(get_db)):
    return rec.run_recommendation(db, session_id, allow_partial=(body.allow_partial if body else False), include_excluded=include_excluded)


@router.get("/sessions/{session_id}/recommendations", response_model=RecommendationOut)
def get_recommendation(session_id: uuid.UUID, include_excluded: bool = Query(False), db: Session = Depends(get_db)):
    return rec.get_recommendation(db, session_id, include_excluded)


# ------------------------------------------------------------------ restaurants and metadata
@router.get("/restaurants/{restaurant_id}", response_model=RestaurantDetail)
def get_restaurant(restaurant_id: uuid.UUID, db: Session = Depends(get_db)):
    return rest.get_detail(db, restaurant_id)


@router.post("/restaurants/{restaurant_id}/reports", status_code=201)
def report_restaurant(restaurant_id: uuid.UUID, body: ReportIn, db: Session = Depends(get_db)):
    """'Report a mistake'. Only queues the report for a human reviewer; it never changes what the engine sees. Rate limited (see services/reports.py)."""
    r = reports.create_report(db, restaurant_id, body)
    return {"report_id": r.report_id, "status": r.status, "message": "已收到回報，審核人員會查證；在查證前不會改變推薦結果。"}


@router.get("/meta/diet-types")
def meta_diet_types():
    """The dining-type quiz (9 questions, 3 axes) and the 8 types with the cuisines each one suggests. A fun shortcut: it never changes the recommendation rules."""
    return diet_type.meta()


@router.put("/participants/{participant_id}/diet-type")
def put_diet_type(participant_id: uuid.UUID, body: DietTypeIn, db: Session = Depends(get_db)):
    """Scores the quiz and stores ONLY the resulting type (not the answers). Retaking replaces it."""
    p = sess.get_participant(db, participant_id)
    sess.get_open_session(db, p.session_id)
    try:
        code = diet_type.score(body.answers)
    except ValueError as e:
        raise AppError(422, "bad_quiz_answers", str(e)) from e
    p.diet_type = code
    db.commit()
    return diet_type.describe(code)


@router.get("/sessions/{session_id}/diet-types")
def get_diet_types(session_id: uuid.UUID, db: Session = Depends(get_db)):
    """Group composition: counts only (no names), hidden until at least 2 people took the quiz."""
    s = sess.get_session(db, session_id)
    codes = [c for c in db.scalars(select(Participant.diet_type).where(Participant.session_id == s.session_id, Participant.diet_type.is_not(None)))]
    return diet_type.composition(codes, sess.participant_count(db, s.session_id))


@router.get("/meta/attributes")
def meta_attributes(db: Session = Depends(get_db)):
    attrs = {a.attribute_code: a for a in db.scalars(select(Attribute).where(Attribute.is_active))}
    groups = []
    for key, label, codes in ATTRIBUTE_GROUPS:
        groups.append({"key": key, "label": label, "items": [
            {"attribute_code": c, "label": attrs[c].display_name_zh, "type": attrs[c].attribute_type, "risk_level": attrs[c].risk_level, "description": attrs[c].description}
            for c in codes if c in attrs]})
    reasons = [{"reason": r.reason, "label": r.label_zh} for r in db.scalars(select(ConstraintReason))]
    return {"groups": groups, "reasons": reasons, "privacy_note": "其他人不會看到你的個人需求。"}


@router.get("/meta/cuisines")
def meta_cuisines():
    return {"chips": [{"tag": t, "label": l} for t, l in CUISINE_CHIPS], "stances": [{"stance": s, "label": l} for s, l in STANCES]}


@router.get("/meta/locations")
def meta_locations():
    return {"locations": LOCATION_PRESETS}
