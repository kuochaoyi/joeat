"""Time poll and restaurant vote endpoints. The participant id is the capability (as everywhere else); host-only actions check it against the session host."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.errors import not_found
from app.models.product import Vote
from app.services import sessions as sess
from app.services import time_polls, votes

router = APIRouter()


class TimeVotesIn(BaseModel):
    option_ids: list[int] = Field(default_factory=list, max_length=30)


class NeedsIn(BaseModel):
    participant_id: uuid.UUID
    needs_pets: bool
    needs_kids: bool


class HostActionIn(BaseModel):
    participant_id: uuid.UUID


class VoteStartIn(BaseModel):
    participant_id: uuid.UUID
    closes_in_hours: int | None = Field(default=None, ge=1, le=168)


class BallotEntry(BaseModel):
    restaurant_id: uuid.UUID
    score: int = Field(default=5, ge=0, le=10)       # 0 = would rather not ... 10 = really want to
    any_ok: bool = False                             # "anything is fine": recorded as the neutral 5


class BallotIn(BaseModel):
    participant_id: uuid.UUID
    scores: list[BallotEntry] = Field(max_length=10)


# ------------------------------------------------------------------ group needs (pet / child)
@router.put("/sessions/{session_id}/needs")
def put_needs(session_id: uuid.UUID, body: NeedsIn, db: Session = Depends(get_db)):
    """The host changes who is coming along. Applies to recommendations generated afterwards (run it again)."""
    s = sess.get_open_session(db, session_id)
    time_polls.require_host(s, sess.get_participant(db, body.participant_id))
    s.needs_pets, s.needs_kids = body.needs_pets, body.needs_kids
    db.commit()
    return {"needs_pets": s.needs_pets, "needs_kids": s.needs_kids}


# ------------------------------------------------------------------ time poll
@router.get("/sessions/{session_id}/time-poll")
def get_time_poll(session_id: uuid.UUID, participant_id: uuid.UUID | None = Query(None), db: Session = Depends(get_db)):
    return time_polls.state(db, sess.get_session(db, session_id), participant_id)


@router.put("/participants/{participant_id}/time-votes")
def put_time_votes(participant_id: uuid.UUID, body: TimeVotesIn, db: Session = Depends(get_db)):
    """Replaces the slots this participant can make. Only counts per slot are ever shown to others."""
    p = sess.get_participant(db, participant_id)
    return time_polls.submit(db, sess.get_open_session(db, p.session_id), p, body.option_ids)


@router.post("/sessions/{session_id}/time-poll/close")
def close_time_poll(session_id: uuid.UUID, body: HostActionIn, db: Session = Depends(get_db)):
    return time_polls.host_close(db, sess.get_session(db, session_id), sess.get_participant(db, body.participant_id))


# ------------------------------------------------------------------ restaurant vote
@router.post("/sessions/{session_id}/votes", status_code=201)
def start_vote(session_id: uuid.UUID, body: VoteStartIn, db: Session = Depends(get_db)):
    """Starts a vote over the latest recommendation's Top 3. Host only (any member when the session has no host)."""
    s = sess.get_open_session(db, session_id)
    v = votes.start(db, s, sess.get_participant(db, body.participant_id), body.closes_in_hours)
    return votes.state(db, s, body.participant_id) | {"vote_id": v.vote_id}


@router.get("/sessions/{session_id}/votes/current")
def get_vote(session_id: uuid.UUID, participant_id: uuid.UUID | None = Query(None), db: Session = Depends(get_db)):
    return votes.state(db, sess.get_session(db, session_id), participant_id)


def _vote(db: Session, vote_id: uuid.UUID) -> Vote:
    v = db.scalar(select(Vote).where(Vote.vote_id == vote_id))
    if v is None:
        raise not_found("vote")
    return v


@router.put("/votes/{vote_id}/ballot")
def put_ballot(vote_id: uuid.UUID, body: BallotIn, db: Session = Depends(get_db)):
    """Replaces this participant's ballot: a 0-10 slider (or 'anything is fine') for every restaurant. Nobody else can see it."""
    v = _vote(db, vote_id)
    votes.submit_ballot(db, v, sess.get_participant(db, body.participant_id), [e.model_dump() for e in body.scores])
    return votes.state(db, sess.get_session(db, v.session_id), body.participant_id)


@router.post("/votes/{vote_id}/close")
def close_vote(vote_id: uuid.UUID, body: HostActionIn, db: Session = Depends(get_db)):
    v = _vote(db, vote_id)
    votes.host_close(db, v, sess.get_participant(db, body.participant_id))
    return votes.state(db, sess.get_session(db, v.session_id), body.participant_id)
