"""Withdraw a published declaration (positive claims stop counting at once; risk claims stay until they expire).

Revision ID: 0006
Revises: 0005
"""
from pathlib import Path

from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None

SQL_DIR = Path(__file__).resolve().parents[2] / "app" / "db" / "sql"


def upgrade() -> None:
    raw = op.get_bind().connection
    with raw.cursor() as cur:
        cur.execute((SQL_DIR / "0006_withdraw_declaration.sql").read_text(encoding="utf-8"))


def downgrade() -> None:
    op.execute("DROP FUNCTION merchant.withdraw_declaration(BIGINT, TEXT, TEXT)")
