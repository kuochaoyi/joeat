"""MVP columns the validated schema did not need yet.

- product.dining_session.title / location_label : the create-session form (name, place)
- product.participant.constraints_submitted_at / preferences_submitted_at : "I have nothing to declare" must be distinguishable from "not filled yet"

Revision ID: 0002
Revises: 0001
"""
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE product.dining_session ADD COLUMN title TEXT")
    op.execute("ALTER TABLE product.dining_session ADD COLUMN location_label TEXT")
    op.execute("ALTER TABLE product.participant ADD COLUMN constraints_submitted_at TIMESTAMPTZ")
    op.execute("ALTER TABLE product.participant ADD COLUMN preferences_submitted_at TIMESTAMPTZ")
    op.execute("CREATE INDEX session_group_ref ON product.dining_session (line_group_ref) WHERE line_group_ref IS NOT NULL")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS product.session_group_ref")
    op.execute("ALTER TABLE product.participant DROP COLUMN IF EXISTS preferences_submitted_at")
    op.execute("ALTER TABLE product.participant DROP COLUMN IF EXISTS constraints_submitted_at")
    op.execute("ALTER TABLE product.dining_session DROP COLUMN IF EXISTS location_label")
    op.execute("ALTER TABLE product.dining_session DROP COLUMN IF EXISTS title")
