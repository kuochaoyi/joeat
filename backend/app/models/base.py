from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Models map onto the tables created by schema_v2.sql (migration 0001); they never create or alter schema."""
