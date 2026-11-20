"""Apply the validated schema_v2.sql (ref / staging / identity / enrichment / product).

Revision ID: 0001
Revises:
"""
from pathlib import Path

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

SQL_FILE = Path(__file__).resolve().parents[2] / "app" / "db" / "sql" / "schema_v2.sql"


def upgrade() -> None:
    sql = SQL_FILE.read_text(encoding="utf-8")
    # Multi-statement script incl. $$ function bodies: run through the raw DBAPI connection (simple query protocol).
    raw = op.get_bind().connection
    with raw.cursor() as cur:
        cur.execute(sql)


def downgrade() -> None:
    for schema in ("product", "enrichment", "identity", "staging", "ref"):
        op.execute(f"DROP SCHEMA IF EXISTS {schema} CASCADE")
