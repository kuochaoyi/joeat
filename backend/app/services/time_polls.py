"""Time poll: the members tick the time slots they can make; the host only sets the deadline (user-testing feedback #2).

The poll closes when the deadline passes, when the host closes it, or when everybody expected (party_size) has answered. The slot with the most
people wins (ties: the earliest) and becomes the session's meal_time. Individual answers are never exposed: only per-slot counts and your own ticks.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models.product import DiningSession, Participant, TimeOption, TimeResponse
from app.services import sessions as sess


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _options(db: Session, s: DiningSession) -> list[TimeOption]:
    return list(db.scalars(select(TimeOption).where(TimeOption.session_id == s.session_id).order_by(TimeOption.starts_at)))


def _counts(db: Session, option_ids: list[int]) -> dict[int, int]:
    if not option_ids:
        return {}
    return dict(db.execute(select(TimeResponse.option_id, func.count()).where(TimeResponse.option_id.in_(option_ids)).group_by(TimeResponse.option_id)).all())


def _responders(db: Session, option_ids: list[int]) -> int:
    if not option_ids:
        return 0
    return db.scalar(select(func.count(func.distinct(TimeResponse.participant_id))).where(TimeResponse.option_id.in_(option_ids))) or 0


def _close(db: Session, s: DiningSession) -> None:
    opts = _options(db, s)
    counts = _counts(db, [o.option_id for o in opts])
    best = max(opts, key=lambda o: (counts.get(o.option_id, 0), -o.starts_at.timestamp()), default=None)      # most people; ties -> the earliest
    if best is not None and counts.get(best.option_id, 0) > 0:
        s.meal_time = best.starts_at
    s.time_closed_at = _now()
    db.commit()


def close_if_due(db: Session, s: DiningSession) -> None:
    """Lazy: evaluated whenever the session or the poll is read or answered."""
    if s.time_mode != "poll" or s.time_closed_at is not None:
        return
    opts = _options(db, s)
    everyone = bool(s.party_size) and _responders(db, [o.option_id for o in opts]) >= s.party_size
    if (s.time_deadline is not None and s.time_deadline <= _now()) or everyone:
        _close(db, s)


def require_host(s: DiningSession, p: Participant) -> None:
    """A session without a host (created from the LINE bot) lets any member close things; with a host, only the host may."""
    if p.session_id != s.session_id:
        raise AppError(403, "not_a_member", "this participant does not belong to this session")
    if s.host_ref is not None and not sess.is_host(s, p):
        raise AppError(403, "host_only", "only the host can do this")


def state(db: Session, s: DiningSession, participant_id: uuid.UUID | None) -> dict:
    if s.time_mode != "poll":
        raise AppError(404, "no_time_poll", "this session has a fixed time")
    close_if_due(db, s)
    opts = _options(db, s)
    ids = [o.option_id for o in opts]
    counts = _counts(db, ids)
    mine = set(db.scalars(select(TimeResponse.option_id).where(TimeResponse.participant_id == participant_id, TimeResponse.option_id.in_(ids)))) if participant_id and ids else set()
    chosen = next((o.option_id for o in opts if s.meal_time is not None and o.starts_at == s.meal_time), None)
    return {
        "session_id": s.session_id, "closed": s.time_closed_at is not None, "deadline": s.time_deadline, "meal_time": s.meal_time, "chosen_option_id": chosen,
        "responded": _responders(db, ids), "joined": sess.participant_count(db, s.session_id), "party_size": s.party_size,
        "options": [{"option_id": o.option_id, "starts_at": o.starts_at, "count": counts.get(o.option_id, 0), "mine": o.option_id in mine} for o in opts],
    }


def submit(db: Session, s: DiningSession, p: Participant, option_ids: list[int]) -> dict:
    if p.session_id != s.session_id:
        raise AppError(403, "not_a_member", "this participant does not belong to this session")
    if s.time_mode != "poll":
        raise AppError(404, "no_time_poll", "this session has a fixed time")
    close_if_due(db, s)
    if s.time_closed_at is not None:
        raise AppError(409, "poll_closed", "the time poll is closed")
    opts = {o.option_id for o in _options(db, s)}
    if not set(option_ids) <= opts:
        raise AppError(422, "unknown_option", "unknown time slot")
    db.execute(delete(TimeResponse).where(TimeResponse.participant_id == p.participant_id, TimeResponse.option_id.in_(opts)))
    for oid in sorted(set(option_ids)):
        db.add(TimeResponse(option_id=oid, participant_id=p.participant_id))
    db.commit()
    return state(db, s, p.participant_id)


def host_close(db: Session, s: DiningSession, p: Participant) -> dict:
    if s.time_mode != "poll":
        raise AppError(404, "no_time_poll", "this session has a fixed time")
    require_host(s, p)
    if s.time_closed_at is None:
        _close(db, s)
    return state(db, s, p.participant_id)
