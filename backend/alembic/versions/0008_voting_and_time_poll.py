"""User-testing feedback: party size 20, session host, time poll, restaurant vote.

Revision ID: 0008
Revises: 0007
"""
from pathlib import Path

from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None

SQL_DIR = Path(__file__).resolve().parents[2] / "app" / "db" / "sql"


def upgrade() -> None:
    raw = op.get_bind().connection
    with raw.cursor() as cur:
        cur.execute((SQL_DIR / "0008_voting_and_time_poll.sql").read_text(encoding="utf-8"))


def downgrade() -> None:
    op.execute("DROP TABLE product.vote_ballot, product.vote_option, product.vote, product.time_response, product.time_option")
    op.execute("ALTER TABLE product.dining_session DROP COLUMN host_ref, DROP COLUMN time_mode, DROP COLUMN time_deadline, DROP COLUMN time_closed_at")
    # sessions with more than 10 people cannot go back under the old limit
    op.execute("UPDATE product.dining_session SET party_size = 10 WHERE party_size > 10")
    op.execute("ALTER TABLE product.dining_session DROP CONSTRAINT session_party_size")
    op.execute("ALTER TABLE product.dining_session ADD CONSTRAINT session_party_size CHECK (party_size IS NULL OR party_size BETWEEN 2 AND 10)")
