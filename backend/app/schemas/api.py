"""Request / response models. Responses are group-level: no participant's individual constraints are ever returned."""
from __future__ import annotations

import uuid
import datetime as dt
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

Stance = Literal["love", "ok", "any", "dislike"]


class SessionCreate(BaseModel):
    title: str = Field(min_length=1, max_length=80)
    date: dt.date | None = None                    # e.g. 2026-11-14
    time: dt.time | None = None                    # e.g. 18:30 (Taiwan time)
    location_label: str | None = Field(default=None, max_length=80)
    location_preset: str | None = None              # key from /meta/locations; gives meeting coordinates
    meeting_lat: float | None = Field(default=None, ge=-90, le=90)
    meeting_lon: float | None = Field(default=None, ge=-180, le=180)
    party_size: int | None = Field(default=None, ge=2, le=20)   # expected head-count (2-20); the LINE bot may leave it open
    line_group_id: str | None = None                # raw LINE group id; hashed immediately, never stored
    host_line_user_id: str | None = Field(default=None, max_length=128)   # the creator: becomes the session host (hashed immediately). Absent = no host powers
    host_id_token: str | None = None                # LIFF ID token for the host (AUTH_MODE=line)
    time_mode: Literal["fixed", "poll"] = "fixed"   # poll = members tick the times they can make; the host only sets the deadline
    time_slots: list[dt.datetime] = Field(default_factory=list, max_length=30)    # candidate start times for a poll (naive = Taiwan time)
    time_deadline_hours: int | None = Field(default=None, ge=1, le=168)           # poll deadline, hours from now (default 24)
    needs_pets: bool = False                        # group need chosen by the host: someone brings a pet (restaurants that explicitly refuse pets are excluded)
    needs_kids: bool = False                        # ... brings a child (only ever a warning)


class SessionOut(BaseModel):
    session_id: uuid.UUID
    title: str | None
    area: str
    location_label: str | None
    meeting_lat: float | None
    meeting_lon: float | None
    meal_time: datetime | None
    party_size: int | None
    status: str
    participant_count: int
    expires_at: datetime
    time_mode: str = "fixed"
    time_deadline: datetime | None = None
    time_closed: bool = False
    outside_coverage: bool = False                  # the meeting point is far from 鹽埕區, the only area with restaurant data
    needs_pets: bool = False
    needs_kids: bool = False


class ParticipantCreate(BaseModel):
    line_user_id: str = Field(min_length=1, max_length=128)    # raw LIFF userId (dev mode) - hashed immediately
    label: str | None = Field(default=None, max_length=20)     # short nickname shown to the group; not a real name
    id_token: str | None = None                                # LIFF ID token (AUTH_MODE=line)


class ParticipantOut(BaseModel):
    participant_id: uuid.UUID
    session_id: uuid.UUID
    label: str | None
    constraints_submitted: bool
    preferences_submitted: bool
    is_host: bool = False


class ConstraintItem(BaseModel):
    attribute_code: str
    reason: str | None = None                       # allergy | medical | religion | belief_diet | dislike | unspecified


class ConstraintsSubmit(BaseModel):
    items: list[ConstraintItem] = Field(default_factory=list, max_length=20)
    budget_max_per_person: int | None = Field(default=None, gt=0, le=100000)    # SOFT only; never excludes
    strict_allergy: bool = False                    # opt in: only restaurants with a confirmed absence pass this member's safety constraints

    @field_validator("items")
    @classmethod
    def unique_codes(cls, v: list[ConstraintItem]) -> list[ConstraintItem]:
        codes = [i.attribute_code for i in v]
        if len(codes) != len(set(codes)):
            raise ValueError("duplicate attribute_code")
        return v


class DietTypeIn(BaseModel):
    answers: dict[str, str] = Field(max_length=9)   # question id -> the chosen letter (see /meta/diet-types)


class ReportIn(BaseModel):
    participant_id: uuid.UUID                       # capability: only people who joined a session can report (rate limit key; never shown to reviewers)
    kind: Literal["wrong_info", "allergic_reaction", "closed", "other"]
    attribute_code: str | None = None
    note: str | None = Field(default=None, max_length=300)


class PreferenceItem(BaseModel):
    cuisine_tag: str
    stance: Stance


class PreferencesSubmit(BaseModel):
    items: list[PreferenceItem] = Field(default_factory=list, max_length=40)

    @field_validator("items")
    @classmethod
    def unique_tags(cls, v: list[PreferenceItem]) -> list[PreferenceItem]:
        tags = [i.cuisine_tag for i in v]
        if len(tags) != len(set(tags)):
            raise ValueError("duplicate cuisine_tag")
        return v


class ProgressParticipant(BaseModel):
    # No participant_id here on purpose: in the MVP the id is the capability to act as that participant, so it must never be shown to the others.
    label: str | None
    is_me: bool = False
    constraints_done: bool
    preferences_done: bool


class ProgressOut(BaseModel):
    session_id: uuid.UUID
    party_size: int | None
    joined: int
    constraints_done: int
    preferences_done: int
    participants: list[ProgressParticipant]
    all_complete: bool
    ready_for_recommendation: bool
    missing_count: int


class RecommendationRequest(BaseModel):
    allow_partial: bool = False                     # run even if some joined members have not finished


class ScoreOut(BaseModel):
    cuisine: float
    distance: float
    data_confidence: float
    rating: float | None
    total: float


class HardConstraintStatus(BaseModel):
    status: Literal["no_constraints", "no_known_conflict", "partial_conflict", "suspected_conflict"]
    unknown_attributes: list[str]
    confirmed_safe: list[str]
    note: str


class WarningOut(BaseModel):
    code: str
    level: str
    text: str
    attribute: str | None = None
    display: str | None = None


class NeedOut(BaseModel):
    """How one restaurant fits a group need (bringing a pet / a child). `status`: yes | no | maybe | unknown."""
    code: str
    name: str
    status: str
    text: str


class DeclarationOut(BaseModel):
    """A merchant's dated statement of fact about one attribute (never a safety claim)."""
    attribute: str
    display: str
    text: str
    verified: bool                  # a reviewer verified the claimant by a strong method


class RestaurantRecommendation(BaseModel):
    rank: int
    restaurant_id: uuid.UUID
    name: str
    address: str | None
    phone: str | None
    cuisines: list[str]
    distance_m: int | None
    score: ScoreOut
    hard_constraint: HardConstraintStatus
    warnings: list[WarningOut]
    reasons: list[str]
    summary: str
    declarations: list[DeclarationOut] = Field(default_factory=list)
    needs: list[NeedOut] = Field(default_factory=list)


class ExcludedOut(BaseModel):
    restaurant_id: uuid.UUID
    name: str
    reasons: list[str]


class RecommendationOut(BaseModel):
    run_id: uuid.UUID
    session_id: uuid.UUID
    created_at: datetime
    scoring_version: str
    participants: int
    party_size: int | None = None
    pool_size: int
    excluded_count: int
    eligible_count: int
    top3: list[RestaurantRecommendation]
    test_evidence_enabled: bool = False                # true = fake (test / demo) evidence is visible to the engine: the UI must say so
    strict_mode: bool = False                          # some member opted in to strict allergy mode (group level: not who)
    excluded: list[ExcludedOut] | None = None
    disclaimer: str = "推薦只依據目前蒐集到的資料。標示「資訊不足」的項目代表我們無法確認，不代表安全；過敏或嚴格飲食請務必向店家確認。"


class RestaurantDetail(BaseModel):
    restaurant_id: uuid.UUID
    name: str
    address: str | None
    phone: str | None
    lat: float | None
    lon: float | None
    district: str
    cuisines: list[dict]
    active_status: str
    pool_status: str
    opening_hours: list[dict]
    attributes: list[dict]
    sources: list[dict]
    notes: list[str]
