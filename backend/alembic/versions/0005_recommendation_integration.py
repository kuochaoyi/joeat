"""Recommendation integration: strict allergy mode flag + report-a-mistake queue.

Revision ID: 0005
Revises: 0004
"""
from pathlib import Path

from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None

SQL_DIR = Path(__file__).resolve().parents[2] / "app" / "db" / "sql"


def upgrade() -> None:
    raw = op.get_bind().connection
    with raw.cursor() as cur:
        cur.execute((SQL_DIR / "0005_recommendation_integration.sql").read_text(encoding="utf-8"))


def downgrade() -> None:
    op.execute("DROP TABLE product.restaurant_report")
    op.execute("ALTER TABLE product.participant DROP COLUMN strict_allergy")
