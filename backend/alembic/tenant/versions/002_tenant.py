"""contacts and accounts tables

Revision ID: 002_tenant
Revises: 001_tenant
"""

from alembic import op

revision = "002_tenant"
down_revision = "001_tenant"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE accounts (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            name TEXT NOT NULL,
            industry TEXT,
            region TEXT,
            website TEXT,
            phone TEXT,
            notes TEXT,
            owner_user_id UUID,
            archived_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX accounts_name_idx ON accounts (lower(name))")
    op.execute(
        "CREATE INDEX accounts_active_idx ON accounts (archived_at) "
        "WHERE archived_at IS NULL"
    )
    op.execute(
        """
        CREATE TABLE contacts (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            account_id UUID REFERENCES accounts(id) ON DELETE SET NULL,
            full_name TEXT NOT NULL,
            job_title TEXT,
            primary_email TEXT,
            primary_phone TEXT,
            emails JSONB NOT NULL DEFAULT '[]',
            phones JSONB NOT NULL DEFAULT '[]',
            social JSONB NOT NULL DEFAULT '{}',
            address TEXT,
            notes TEXT,
            owner_user_id UUID,
            consent_status TEXT NOT NULL DEFAULT 'unknown'
                CHECK (consent_status IN ('unknown','granted','denied')),
            consent_basis TEXT
                CHECK (consent_basis IS NULL OR consent_basis IN
                    ('consentimiento','contrato','interes_legitimo','obligacion_legal')),
            consent_recorded_at TIMESTAMPTZ,
            archived_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX contacts_name_idx ON contacts (lower(full_name))")
    op.execute("CREATE INDEX contacts_email_idx ON contacts (lower(primary_email))")
    op.execute("CREATE INDEX contacts_account_idx ON contacts (account_id)")
    op.execute(
        "CREATE INDEX contacts_active_idx ON contacts (archived_at) "
        "WHERE archived_at IS NULL"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS contacts")
    op.execute("DROP TABLE IF EXISTS accounts")
