from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, SmallInteger, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Attribute(Base):
    __tablename__ = "attribute"
    __table_args__ = {"schema": "ref"}
    attribute_code: Mapped[str] = mapped_column(Text, primary_key=True)
    display_name_zh: Mapped[str] = mapped_column(Text)
    attribute_type: Mapped[str] = mapped_column(Text)          # avoid | require
    risk_level: Mapped[str] = mapped_column(Text)              # critical | high | normal
    description: Mapped[str] = mapped_column(Text)
    default_unknown_behavior: Mapped[str] = mapped_column(Text)
    sort_order: Mapped[int] = mapped_column(SmallInteger)
    is_active: Mapped[bool] = mapped_column(Boolean)
    default_constraint_class: Mapped[str] = mapped_column(Text, default="preference")      # migration 0003: safety | preference


class ConstraintReason(Base):
    __tablename__ = "constraint_reason"
    __table_args__ = {"schema": "ref"}
    reason: Mapped[str] = mapped_column(Text, primary_key=True)
    min_risk_level: Mapped[str] = mapped_column(Text)
    label_zh: Mapped[str] = mapped_column(Text)
    constraint_class: Mapped[str] = mapped_column(Text, default="preference")               # migration 0003: safety | preference


class ConstraintDecisionRule(Base):
    __tablename__ = "constraint_decision_rule"
    __table_args__ = {"schema": "ref"}
    attribute_type: Mapped[str] = mapped_column(Text, primary_key=True)
    risk_level: Mapped[str] = mapped_column(Text, primary_key=True)
    state: Mapped[str] = mapped_column(String, primary_key=True)      # ref.evidence_state enum, read as text
    action: Mapped[str] = mapped_column(Text)
    warning_level: Mapped[str] = mapped_column(Text)
    may_show_safe_badge: Mapped[bool] = mapped_column(Boolean)
    note: Mapped[str | None] = mapped_column(Text)


class ScoringConfig(Base):
    __tablename__ = "scoring_config"
    __table_args__ = {"schema": "ref"}
    version: Mapped[str] = mapped_column(Text, primary_key=True)
    config: Mapped[dict] = mapped_column(JSONB)
    is_active: Mapped[bool] = mapped_column(Boolean)
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class CuisineTag(Base):
    __tablename__ = "cuisine_tag"
    __table_args__ = {"schema": "ref"}
    tag: Mapped[str] = mapped_column(Text, primary_key=True)
    parent_tag: Mapped[str | None] = mapped_column(Text, ForeignKey("ref.cuisine_tag.tag"))
