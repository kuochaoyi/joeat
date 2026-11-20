import uuid
from datetime import date, datetime

from sqlalchemy import BigInteger, Date, DateTime, Float, ForeignKey, SmallInteger, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Restaurant(Base):
    __tablename__ = "restaurant"
    __table_args__ = {"schema": "identity"}
    restaurant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()"))
    canonical_name: Mapped[str] = mapped_column(Text)
    canonical_address: Mapped[str | None] = mapped_column(Text)
    address_key: Mapped[str | None] = mapped_column(Text)
    district: Mapped[str] = mapped_column(Text)
    city: Mapped[str] = mapped_column(Text)
    lat: Mapped[float | None] = mapped_column(Float)
    lon: Mapped[float | None] = mapped_column(Float)
    phone: Mapped[str | None] = mapped_column(Text)
    active_status: Mapped[str] = mapped_column(Text, default="unverified")
    pool_status: Mapped[str] = mapped_column(Text, default="candidate")
    pool_reason: Mapped[str | None] = mapped_column(Text)
    status_verified_at: Mapped[date | None] = mapped_column(Date)
    merged_into_restaurant_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("identity.restaurant.restaurant_id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))


class RestaurantSourceEntity(Base):
    __tablename__ = "restaurant_source_entity"
    __table_args__ = {"schema": "identity"}
    source_entity_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    restaurant_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("identity.restaurant.restaurant_id"))
    source_id: Mapped[int] = mapped_column(SmallInteger)
    source_record_id: Mapped[str] = mapped_column(Text)
    source_name: Mapped[str | None] = mapped_column(Text)
    source_address: Mapped[str | None] = mapped_column(Text)
    match_status: Mapped[str] = mapped_column(Text)
