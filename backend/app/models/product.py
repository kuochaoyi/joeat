import uuid
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, Enum, Float, ForeignKeyConstraint, Integer, Numeric, SmallInteger, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base

EVIDENCE_STATES = ("CONFIRMED_PRESENT", "LIKELY_PRESENT", "LIKELY_ABSENT", "CONFIRMED_ABSENT", "UNKNOWN")
EvidenceStateType = Enum(*EVIDENCE_STATES, name="evidence_state", schema="ref", create_type=False)


def _uuid(**kw):
    return mapped_column(UUID(as_uuid=True), **kw)


class DiningSession(Base):
    __tablename__ = "dining_session"
    __table_args__ = {"schema": "product"}
    session_id: Mapped[uuid.UUID] = _uuid(primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()"))
    line_group_ref: Mapped[str | None] = mapped_column(Text)
    area: Mapped[str] = mapped_column(Text, default="鹽埕區")
    meeting_lat: Mapped[float | None] = mapped_column(Float)
    meeting_lon: Mapped[float | None] = mapped_column(Float)
    radius_m: Mapped[int | None] = mapped_column(Integer)
    meal_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    party_size: Mapped[int | None] = mapped_column(SmallInteger)
    status: Mapped[str] = mapped_column(Text, default="collecting")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now() + interval '7 days'"))
    title: Mapped[str | None] = mapped_column(Text)            # migration 0002
    location_label: Mapped[str | None] = mapped_column(Text)   # migration 0002
    host_ref: Mapped[str | None] = mapped_column(Text)                                                   # migration 0008: hashed creator id (NULL = created from the LINE bot)
    time_mode: Mapped[str] = mapped_column(Text, default="fixed", server_default=text("'fixed'"))        # fixed | poll
    time_deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    time_closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    needs_pets: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))     # migration 0009: the host said someone brings a pet
    needs_kids: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))     # ... a child


class Participant(Base):
    __tablename__ = "participant"
    __table_args__ = {"schema": "product"}
    participant_id: Mapped[uuid.UUID] = _uuid(primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()"))
    session_id: Mapped[uuid.UUID] = _uuid()
    line_user_ref: Mapped[str] = mapped_column(Text)
    label: Mapped[str | None] = mapped_column(Text)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    constraints_submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))   # migration 0002
    preferences_submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))   # migration 0002
    strict_allergy: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))   # migration 0005
    diet_type: Mapped[str | None] = mapped_column(Text)                                                    # migration 0010: 3-letter dining type; never used by the engine


class ParticipantHardConstraint(Base):
    __tablename__ = "participant_hard_constraint"
    __table_args__ = {"schema": "product"}
    participant_id: Mapped[uuid.UUID] = _uuid(primary_key=True)
    attribute_code: Mapped[str] = mapped_column(Text, primary_key=True)
    reason: Mapped[str] = mapped_column(Text, default="unspecified")


class ParticipantBudget(Base):
    """SOFT only. Never used to exclude a restaurant."""
    __tablename__ = "participant_budget"
    __table_args__ = {"schema": "product"}
    participant_id: Mapped[uuid.UUID] = _uuid(primary_key=True)
    max_per_person: Mapped[int] = mapped_column(Integer)


class ParticipantPreference(Base):
    __tablename__ = "participant_preference"
    __table_args__ = {"schema": "product"}
    participant_id: Mapped[uuid.UUID] = _uuid(primary_key=True)
    cuisine_tag: Mapped[str] = mapped_column(Text, primary_key=True)
    stance: Mapped[str] = mapped_column(Text)          # love | ok | any | dislike


class TimeOption(Base):
    __tablename__ = "time_option"
    __table_args__ = {"schema": "product"}
    option_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    session_id: Mapped[uuid.UUID] = _uuid()
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class TimeResponse(Base):
    __tablename__ = "time_response"
    __table_args__ = {"schema": "product"}
    option_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    participant_id: Mapped[uuid.UUID] = _uuid(primary_key=True)


class Vote(Base):
    """Restaurant vote over a run's Top 3: every member moves a 0-10 slider per restaurant (or says 'anything is fine')."""
    __tablename__ = "vote"
    __table_args__ = {"schema": "product"}
    vote_id: Mapped[uuid.UUID] = _uuid(primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()"))
    session_id: Mapped[uuid.UUID] = _uuid()
    run_id: Mapped[uuid.UUID] = _uuid()
    status: Mapped[str] = mapped_column(Text, default="open")
    closes_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    winner_restaurant_id: Mapped[uuid.UUID | None] = _uuid()
    tie_broken: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))


class VoteOption(Base):
    __tablename__ = "vote_option"
    __table_args__ = {"schema": "product"}
    vote_id: Mapped[uuid.UUID] = _uuid(primary_key=True)
    restaurant_id: Mapped[uuid.UUID] = _uuid(primary_key=True)
    rank: Mapped[int] = mapped_column(SmallInteger)
    snapshot: Mapped[dict] = mapped_column(JSONB)


class VoteBallot(Base):
    __tablename__ = "vote_ballot"
    __table_args__ = {"schema": "product"}
    vote_id: Mapped[uuid.UUID] = _uuid(primary_key=True)
    participant_id: Mapped[uuid.UUID] = _uuid(primary_key=True)
    restaurant_id: Mapped[uuid.UUID] = _uuid(primary_key=True)
    score: Mapped[int] = mapped_column(SmallInteger)
    any_ok: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))


class RestaurantReport(Base):
    """'Report a mistake'. Never changes data by itself: a reviewer dismisses it or escalates it to a merchant incident."""
    __tablename__ = "restaurant_report"
    __table_args__ = {"schema": "product"}
    report_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    restaurant_id: Mapped[uuid.UUID] = _uuid()
    attribute_code: Mapped[str | None] = mapped_column(Text)
    participant_id: Mapped[uuid.UUID | None] = _uuid()
    kind: Mapped[str] = mapped_column(Text)
    note: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, default="open")
    incident_id: Mapped[int | None] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))
    handled_by: Mapped[str | None] = mapped_column(Text)
    handled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    handled_note: Mapped[str | None] = mapped_column(Text)


class RecommendationRun(Base):
    __tablename__ = "recommendation_run"
    __table_args__ = {"schema": "product"}
    run_id: Mapped[uuid.UUID] = _uuid(primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()"))
    session_id: Mapped[uuid.UUID] = _uuid()
    scoring_version: Mapped[str] = mapped_column(Text)
    config_snapshot: Mapped[dict] = mapped_column(JSONB)
    data_snapshot_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    pool_size: Mapped[int | None] = mapped_column(Integer)
    excluded_count: Mapped[int | None] = mapped_column(Integer)
    eligible_count: Mapped[int | None] = mapped_column(Integer)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))


class RecommendationCandidate(Base):
    __tablename__ = "recommendation_candidate"
    __table_args__ = {"schema": "product"}
    run_id: Mapped[uuid.UUID] = _uuid(primary_key=True)
    restaurant_id: Mapped[uuid.UUID] = _uuid(primary_key=True)
    stage: Mapped[str] = mapped_column(Text)            # excluded | eligible | top3
    distance_m: Mapped[int | None] = mapped_column(Integer)
    cuisine_score: Mapped[float | None] = mapped_column(Numeric(6, 2))
    distance_score: Mapped[float | None] = mapped_column(Numeric(6, 2))
    data_confidence_score: Mapped[float | None] = mapped_column(Numeric(6, 2))
    rating_score: Mapped[float | None] = mapped_column(Numeric(6, 2))
    total_score: Mapped[float | None] = mapped_column(Numeric(7, 2))
    rank: Mapped[int | None] = mapped_column(SmallInteger)
    warning_count: Mapped[int] = mapped_column(Integer, default=0)
    critical_warning_count: Mapped[int] = mapped_column(Integer, default=0)
    warnings: Mapped[list] = mapped_column(JSONB, default=list)
    explanation: Mapped[dict | None] = mapped_column(JSONB)


class RecommendationConstraintCheck(Base):
    __tablename__ = "recommendation_constraint_check"
    __table_args__ = (
        ForeignKeyConstraint(["run_id", "restaurant_id"], ["product.recommendation_candidate.run_id", "product.recommendation_candidate.restaurant_id"]),
        {"schema": "product"},
    )
    check_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    run_id: Mapped[uuid.UUID] = _uuid()
    session_id: Mapped[uuid.UUID] = _uuid()
    restaurant_id: Mapped[uuid.UUID] = _uuid()
    participant_id: Mapped[uuid.UUID] = _uuid()
    attribute_code: Mapped[str] = mapped_column(Text)
    attribute_type: Mapped[str] = mapped_column(Text)
    effective_risk_level: Mapped[str] = mapped_column(Text)
    evidence_state: Mapped[str] = mapped_column(EvidenceStateType)
    action: Mapped[str] = mapped_column(Text)
    warning_level: Mapped[str] = mapped_column(Text)
    may_show_safe_badge: Mapped[bool] = mapped_column(Boolean, default=False)
    deciding_evidence_id: Mapped[int | None] = mapped_column(BigInteger)
    evidence_snapshot: Mapped[dict | None] = mapped_column(JSONB)
    message_zh: Mapped[str | None] = mapped_column(Text)


class RecommendationScoreComponent(Base):
    __tablename__ = "recommendation_score_component"
    __table_args__ = (
        ForeignKeyConstraint(["run_id", "restaurant_id"], ["product.recommendation_candidate.run_id", "product.recommendation_candidate.restaurant_id"]),
        {"schema": "product"},
    )
    component_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    run_id: Mapped[uuid.UUID] = _uuid()
    session_id: Mapped[uuid.UUID] = _uuid()
    restaurant_id: Mapped[uuid.UUID] = _uuid()
    component: Mapped[str] = mapped_column(Text)
    participant_id: Mapped[uuid.UUID | None] = _uuid()
    raw_value: Mapped[str | None] = mapped_column(Text)
    points: Mapped[float] = mapped_column(Numeric(6, 2), default=0)
    detail: Mapped[dict | None] = mapped_column(JSONB)
