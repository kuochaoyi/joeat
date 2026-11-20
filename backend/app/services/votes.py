"""Restaurant vote over a recommendation run's Top 3 (user-testing feedback: sliders instead of pick-one-of-three).

Every member moves a 0-10 slider for EVERY restaurant ("anything is fine" = a neutral 5, remembered separately). Nobody sees who voted what: while the
vote is open only the number of ballots is shown; the aggregate appears when it closes (deadline, host, or everyone has voted).
Winner = highest total score; ties go to the higher lowest score (the option nobody dislikes), then more enthusiastic votes (>= 8), then the better
recommendation rank. Only restaurants that already passed every hard constraint can be on the ballot.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core.errors import AppError, not_found
from app.models.product import DiningSession, Participant, RecommendationRun, Vote, VoteBallot, VoteOption
from app.services import recommendations as rec
from app.services import sessions as sess
from app.services.time_polls import require_host

NEUTRAL = 5


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _snapshot(item: dict) -> dict:
    keep = ("name", "address", "cuisines", "distance_m", "reasons")
    snap = {k: item.get(k) for k in keep}
    snap["warnings"] = [{"level": w["level"], "text": w["text"]} for w in item.get("warnings", []) if w["level"] in ("critical", "high")]
    snap["declarations"] = [{"display": d["display"], "text": d["text"], "verified": d["verified"]} for d in item.get("declarations", [])]
    snap["needs"] = [{"name": n["name"], "status": n["status"], "text": n["text"]} for n in item.get("needs", [])]
    snap["hard_constraint_status"] = item["hard_constraint"]["status"]
    return snap


def start(db: Session, s: DiningSession, p: Participant, closes_in_hours: int | None) -> Vote:
    require_host(s, p)
    close_if_due(db, s)
    if db.scalar(select(func.count()).select_from(Vote).where(Vote.session_id == s.session_id, Vote.status == "open")):
        raise AppError(409, "vote_open", "there is already an open vote for this session")
    try:
        data = rec.get_recommendation(db, s.session_id)
    except AppError as e:
        raise AppError(409, "no_recommendation", "run the recommendation first") from e
    if not data["top3"]:
        raise AppError(409, "nothing_to_vote_on", "the recommendation has no restaurant to vote on")
    v = Vote(session_id=s.session_id, run_id=data["run_id"], closes_at=_now() + timedelta(hours=closes_in_hours or 24))
    db.add(v)
    db.flush()
    for it in data["top3"]:
        db.add(VoteOption(vote_id=v.vote_id, restaurant_id=it["restaurant_id"], rank=it["rank"], snapshot=_snapshot(it)))
    db.commit()
    return v


def current(db: Session, s: DiningSession) -> Vote | None:
    return db.scalars(select(Vote).where(Vote.session_id == s.session_id).order_by(Vote.created_at.desc()).limit(1)).first()


def _voters(db: Session, vote_id: uuid.UUID) -> int:
    return db.scalar(select(func.count(func.distinct(VoteBallot.participant_id))).where(VoteBallot.vote_id == vote_id)) or 0


def _tally(db: Session, v: Vote) -> tuple[list[dict], uuid.UUID | None, bool]:
    options = db.scalars(select(VoteOption).where(VoteOption.vote_id == v.vote_id).order_by(VoteOption.rank)).all()
    ballots = db.scalars(select(VoteBallot).where(VoteBallot.vote_id == v.vote_id)).all()
    rows = []
    for o in options:
        sc = [b.score for b in ballots if b.restaurant_id == o.restaurant_id]
        rows.append({"restaurant_id": o.restaurant_id, "rank": o.rank, "snapshot": o.snapshot, "total": sum(sc), "voters": len(sc),
                     "average": round(sum(sc) / len(sc), 1) if sc else None, "lowest": min(sc) if sc else None,
                     "unhappy": sum(1 for x in sc if x <= 2), "keen": sum(1 for x in sc if x >= 8),
                     "any_ok": sum(1 for b in ballots if b.restaurant_id == o.restaurant_id and b.any_ok)})
    def key(r):
        return (-r["total"], -(r["lowest"] if r["lowest"] is not None else -1), -r["keen"], r["rank"])
    order = sorted(rows, key=key)
    tie = len(order) > 1 and key(order[0])[:3] == key(order[1])[:3]
    winner = order[0]["restaurant_id"] if order and order[0]["voters"] else None
    return order, winner, tie


def close(db: Session, v: Vote) -> None:
    if v.status == "closed":
        return
    _, winner, tie = _tally(db, v)
    v.status, v.closed_at, v.winner_restaurant_id, v.tie_broken = "closed", _now(), winner, tie
    db.commit()


def close_if_due(db: Session, s: DiningSession) -> None:
    v = current(db, s)
    if v is None or v.status == "closed":
        return
    joined = sess.participant_count(db, s.session_id)
    if v.closes_at <= _now() or (joined >= 2 and _voters(db, v.vote_id) >= joined):
        close(db, v)


def state(db: Session, s: DiningSession, participant_id: uuid.UUID | None) -> dict:
    close_if_due(db, s)
    v = current(db, s)
    if v is None:
        raise not_found("vote")
    options = db.scalars(select(VoteOption).where(VoteOption.vote_id == v.vote_id).order_by(VoteOption.rank)).all()
    mine = {b.restaurant_id: b for b in db.scalars(select(VoteBallot).where(VoteBallot.vote_id == v.vote_id, VoteBallot.participant_id == participant_id))} if participant_id else {}
    out = {
        "vote_id": v.vote_id, "status": v.status, "closes_at": v.closes_at, "voted": _voters(db, v.vote_id), "joined": sess.participant_count(db, s.session_id),
        "i_voted": bool(mine),
        "options": [{"restaurant_id": o.restaurant_id, "rank": o.rank, **o.snapshot,
                     "my_score": mine[o.restaurant_id].score if o.restaurant_id in mine else None,
                     "my_any_ok": mine[o.restaurant_id].any_ok if o.restaurant_id in mine else False} for o in options],
        "result": None, "winner_restaurant_id": v.winner_restaurant_id, "tie_broken": v.tie_broken,
    }
    if v.status == "closed":                                    # the aggregate is only shown once the vote is over
        order, _, _ = _tally(db, v)
        out["result"] = [{"restaurant_id": r["restaurant_id"], "name": r["snapshot"]["name"], "total": r["total"], "average": r["average"], "voters": r["voters"],
                          "unhappy": r["unhappy"], "keen": r["keen"], "any_ok": r["any_ok"]} for r in order]
    return out


def submit_ballot(db: Session, v: Vote, p: Participant, entries: list[dict]) -> None:
    s = sess.get_session(db, v.session_id)
    if p.session_id != s.session_id:
        raise AppError(403, "not_a_member", "this participant does not belong to this session")
    close_if_due(db, s)
    db.refresh(v)
    if v.status == "closed":
        raise AppError(409, "vote_closed", "the vote is closed")
    option_ids = {o.restaurant_id for o in db.scalars(select(VoteOption).where(VoteOption.vote_id == v.vote_id))}
    got = {e["restaurant_id"] for e in entries}
    if got != option_ids or len(entries) != len(option_ids):
        raise AppError(422, "incomplete_ballot", "give a score (or 'anything is fine') for every restaurant on the ballot")
    db.execute(delete(VoteBallot).where(VoteBallot.vote_id == v.vote_id, VoteBallot.participant_id == p.participant_id))
    for e in entries:
        any_ok = bool(e.get("any_ok"))
        db.add(VoteBallot(vote_id=v.vote_id, participant_id=p.participant_id, restaurant_id=e["restaurant_id"], score=NEUTRAL if any_ok else e["score"], any_ok=any_ok))
    db.commit()
    close_if_due(db, s)


def host_close(db: Session, v: Vote, p: Participant) -> None:
    s = sess.get_session(db, v.session_id)
    require_host(s, p)
    close(db, v)
