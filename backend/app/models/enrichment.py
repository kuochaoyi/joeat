import uuid
from datetime import date

from sqlalchemy import BigInteger, Date, ForeignKey, SmallInteger, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class RestaurantCuisine(Base):
    __tablename__ = "restaurant_cuisine"
    __table_args__ = {"schema": "enrichment"}
    restaurant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("identity.restaurant.restaurant_id"), primary_key=True)
    tag: Mapped[str] = mapped_column(Text, ForeignKey("ref.cuisine_tag.tag"), primary_key=True)
    origin: Mapped[str] = mapped_column(Text, primary_key=True)
    confidence: Mapped[str] = mapped_column(Text)
    last_verified_at: Mapped[date] = mapped_column(Date)


class RestaurantOpeningHours(Base):
    __tablename__ = "restaurant_opening_hours"
    __table_args__ = {"schema": "enrichment"}
    hours_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    restaurant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("identity.restaurant.restaurant_id"))
    raw_text: Mapped[str] = mapped_column(Text)
    consistency: Mapped[str] = mapped_column(Text)
    source_id: Mapped[int] = mapped_column(SmallInteger)
    source_url: Mapped[str | None] = mapped_column(Text)
    confidence: Mapped[str] = mapped_column(Text)
    last_verified_at: Mapped[date] = mapped_column(Date)


class RestaurantAttributeEvidence(Base):
    __tablename__ = "restaurant_attribute_evidence"
    __table_args__ = {"schema": "enrichment"}
    evidence_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    restaurant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("identity.restaurant.restaurant_id"))
    attribute_code: Mapped[str] = mapped_column(Text, ForeignKey("ref.attribute.attribute_code"))
    state: Mapped[str] = mapped_column(Text)
    evidence_text: Mapped[str | None] = mapped_column(Text)
    evidence_basis: Mapped[str] = mapped_column(Text)
    applies_to: Mapped[str] = mapped_column(Text)
    source_id: Mapped[int] = mapped_column(SmallInteger)
    source_url: Mapped[str | None] = mapped_column(Text)
    confidence: Mapped[str] = mapped_column(Text)
    last_verified_at: Mapped[date] = mapped_column(Date)
    valid_until: Mapped[date | None] = mapped_column(Date)
    declaration_id: Mapped[int | None] = mapped_column(BigInteger)             # migration 0003: set when the evidence came from a merchant declaration
    cross_contact_status: Mapped[str | None] = mapped_column(Text)             # migration 0003
    presence_extent: Mapped[str | None] = mapped_column(Text)                  # migration 0003: some | most
