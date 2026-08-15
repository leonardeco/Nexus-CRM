"""tenant schema tables

Revision ID: 001_tenant
Revises:
"""

from alembic import op

revision = "001_tenant"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE settings (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            company_name TEXT NOT NULL,
            slug TEXT NOT NULL,
            policy_version TEXT NOT NULL,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        """
        CREATE TABLE arco_requests (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            request_type TEXT NOT NULL,
            source TEXT NOT NULL,
            status TEXT NOT NULL,
            requester_name TEXT NOT NULL,
            requester_email TEXT NOT NULL,
            details TEXT,
            response_text TEXT,
            created_by_user_id UUID,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            responded_at TIMESTAMPTZ,
            closed_at TIMESTAMPTZ
        )
        """
    )
    op.execute(
        """
        CREATE TABLE audit_events (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            occurred_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            event_type TEXT NOT NULL,
            actor_email TEXT,
            ip_address TEXT,
            payload JSONB NOT NULL DEFAULT '{}'
        )
        """
    )
    op.execute("REVOKE UPDATE, DELETE ON audit_events FROM PUBLIC")
    op.execute(
        "CREATE RULE audit_events_no_update AS ON UPDATE TO audit_events DO INSTEAD NOTHING"
    )
    op.execute(
        "CREATE RULE audit_events_no_delete AS ON DELETE TO audit_events DO INSTEAD NOTHING"
    )


def downgrade() -> None:
    op.execute("DROP RULE IF EXISTS audit_events_no_delete ON audit_events")
    op.execute("DROP RULE IF EXISTS audit_events_no_update ON audit_events")
    op.execute("DROP TABLE IF EXISTS audit_events")
    op.execute("DROP TABLE IF EXISTS arco_requests")
    op.execute("DROP TABLE IF EXISTS settings")
