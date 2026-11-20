"""Dining type quiz result stored on the participant.

Revision ID: 0010
Revises: 0009
"""
from pathlib import Path

from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None

SQL_DIR = Path(__file__).resolve().parents[2] / "app" / "db" / "sql"


def upgrade() -> None:
    raw = op.get_bind().connection
    with raw.cursor() as cur:
        cur.execute((SQL_DIR / "0010_diet_type.sql").read_text(encoding="utf-8"))


def downgrade() -> None:
    op.execute("ALTER TABLE product.participant DROP COLUMN diet_type")
