"""immutable platform audit events

Revision ID: 002_catalog
Revises: 001_catalog
"""

from alembic import op

revision = "002_catalog"
down_revision = "001_catalog"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("REVOKE UPDATE, DELETE ON catalog.platform_audit_events FROM PUBLIC")
    op.execute(
        """
        CREATE RULE platform_audit_events_no_update
        AS ON UPDATE TO catalog.platform_audit_events DO INSTEAD NOTHING
        """
    )
    op.execute(
        """
        CREATE RULE platform_audit_events_no_delete
        AS ON DELETE TO catalog.platform_audit_events DO INSTEAD NOTHING
        """
    )


def downgrade() -> None:
    op.execute(
        "DROP RULE IF EXISTS platform_audit_events_no_delete ON catalog.platform_audit_events"
    )
    op.execute(
        "DROP RULE IF EXISTS platform_audit_events_no_update ON catalog.platform_audit_events"
    )
