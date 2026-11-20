"""Merchant self-declaration lifecycle (claims, declarations, audit, incidents, evidence lifecycle, safety/preference class data).

Revision ID: 0003
Revises: 0002

The engine is not changed by this revision (see the header of 0003_merchant_declaration.sql).
Downgrade REMOVES everything merchant-derived: first-party evidence written by declarations is deleted along with the schema.
"""
import re
from pathlib import Path

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

SQL_DIR = Path(__file__).resolve().parents[2] / "app" / "db" / "sql"


def upgrade() -> None:
    raw = op.get_bind().connection
    with raw.cursor() as cur:
        cur.execute((SQL_DIR / "0003_merchant_declaration.sql").read_text(encoding="utf-8"))


def downgrade() -> None:
    op.execute("UPDATE enrichment.restaurant_attribute_evidence SET superseded_by = NULL, suspended_by_incident = NULL")
    op.execute("DELETE FROM enrichment.restaurant_attribute_evidence WHERE declaration_id IS NOT NULL")
    op.execute("DROP SCHEMA IF EXISTS merchant CASCADE")
    op.execute("DROP FUNCTION IF EXISTS ref.effective_constraint_class(text, text)")
    op.execute("DELETE FROM ref.evidence_state_basis_rule WHERE state = 'LIKELY_ABSENT' AND basis = 'restaurant_declaration'")
    # Dropping these columns drops the views that were created with `SELECT e.*`; they are recreated from schema_v2.sql afterwards.
    op.execute("""ALTER TABLE enrichment.restaurant_attribute_evidence
                  DROP COLUMN presence_extent CASCADE, DROP COLUMN cross_contact_status CASCADE, DROP COLUMN suspended_by_incident CASCADE,
                  DROP COLUMN declaration_id CASCADE, DROP COLUMN superseded_by CASCADE, DROP COLUMN status CASCADE""")
    op.execute("ALTER TABLE ref.constraint_reason DROP COLUMN constraint_class")
    op.execute("ALTER TABLE ref.attribute DROP COLUMN default_constraint_class")
    schema = (SQL_DIR / "schema_v2.sql").read_text(encoding="utf-8")
    views = re.search(r"(CREATE VIEW enrichment\.v_evidence_valid AS.*?)(?=-- Identity corroboration)", schema, re.S).group(1)
    raw = op.get_bind().connection
    with raw.cursor() as cur:
        cur.execute(views)
