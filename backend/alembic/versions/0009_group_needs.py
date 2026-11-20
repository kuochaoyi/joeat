"""Group needs chosen by the host: bringing a pet / a child.

Revision ID: 0009
Revises: 0008
"""
from pathlib import Path

from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None

SQL_DIR = Path(__file__).resolve().parents[2] / "app" / "db" / "sql"


def upgrade() -> None:
    raw = op.get_bind().connection
    with raw.cursor() as cur:
        cur.execute((SQL_DIR / "0009_group_needs.sql").read_text(encoding="utf-8"))


def downgrade() -> None:
    op.execute("ALTER TABLE product.dining_session DROP COLUMN needs_pets, DROP COLUMN needs_kids")
