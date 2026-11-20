"""Evidence text and customer statements use the merchant's declaration date; the reviewer's name leaves the public evidence text.

Revision ID: 0007
Revises: 0006
"""
from pathlib import Path

from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None

SQL_DIR = Path(__file__).resolve().parents[2] / "app" / "db" / "sql"


def _run(name: str) -> None:
    raw = op.get_bind().connection
    with raw.cursor() as cur:
        cur.execute((SQL_DIR / name).read_text(encoding="utf-8"))


def upgrade() -> None:
    _run("0007_declared_date.sql")


def downgrade() -> None:
    _run("0007_publish_before.sql")
