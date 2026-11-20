"""Demo isolation: claims can be marked demo; their declarations publish into the hidden test source.

Revision ID: 0004
Revises: 0003
"""
from pathlib import Path

from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

SQL_DIR = Path(__file__).resolve().parents[2] / "app" / "db" / "sql"


def _run(name: str) -> None:
    raw = op.get_bind().connection
    with raw.cursor() as cur:
        cur.execute((SQL_DIR / name).read_text(encoding="utf-8"))


def upgrade() -> None:
    _run("0004_demo_isolation.sql")


def downgrade() -> None:
    _run("0003_functions_for_downgrade.sql")          # restore the 0003 bodies first (they do not reference is_demo)
    # Rows that a demo declaration superseded (a reviewer ticked "supersede") point at the evidence we are about to delete: give them back their
    # status first, otherwise the superseded_by foreign key blocks the delete.
    demo = ("SELECT e.evidence_id FROM enrichment.restaurant_attribute_evidence e JOIN ref.data_source s ON s.source_id = e.source_id "
            "WHERE s.source_type = 'test_fixture' AND e.declaration_id IS NOT NULL")
    op.execute(f"UPDATE enrichment.restaurant_attribute_evidence SET status = 'active', superseded_by = NULL WHERE superseded_by IN ({demo})")
    op.execute("DELETE FROM enrichment.restaurant_attribute_evidence e USING ref.data_source s WHERE s.source_id = e.source_id AND s.source_type = 'test_fixture' AND e.declaration_id IS NOT NULL")
    op.execute("ALTER TABLE merchant.claim DROP COLUMN is_demo")
