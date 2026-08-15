"""catalog foundation tables

Revision ID: 001_catalog
Revises:
"""

from alembic import op

revision = "001_catalog"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS catalog")
    op.execute(
        """
        CREATE TABLE catalog.tenants (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            slug TEXT NOT NULL UNIQUE,
            company_name TEXT NOT NULL,
            schema_name TEXT NOT NULL UNIQUE,
            plan TEXT NOT NULL DEFAULT 'starter',
            seat_cap INTEGER NOT NULL DEFAULT 2,
            status TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        """
        CREATE TABLE catalog.users (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id UUID NOT NULL REFERENCES catalog.tenants(id) ON DELETE CASCADE,
            full_name TEXT NOT NULL,
            role TEXT NOT NULL,
            status TEXT NOT NULL,
            mfa_status TEXT NOT NULL,
            password_hash TEXT,
            totp_secret_encrypted BYTEA,
            backup_code_hashes TEXT[],
            email_verified_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            deactivated_at TIMESTAMPTZ
        )
        """
    )
    op.execute(
        """
        CREATE TABLE catalog.email_identities (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id UUID NOT NULL REFERENCES catalog.users(id) ON DELETE CASCADE,
            email TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX email_identities_lower_email_idx
            ON catalog.email_identities (lower(email))
        """
    )
    op.execute(
        """
        CREATE TABLE catalog.email_verify_tokens (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id UUID NOT NULL REFERENCES catalog.users(id) ON DELETE CASCADE,
            token_hash TEXT NOT NULL UNIQUE,
            expires_at TIMESTAMPTZ NOT NULL,
            consumed_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        """
        CREATE TABLE catalog.password_reset_tokens (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id UUID NOT NULL REFERENCES catalog.users(id) ON DELETE CASCADE,
            token_hash TEXT NOT NULL UNIQUE,
            expires_at TIMESTAMPTZ NOT NULL,
            consumed_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        """
        CREATE TABLE catalog.invites (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id UUID NOT NULL REFERENCES catalog.tenants(id) ON DELETE CASCADE,
            email TEXT NOT NULL,
            role TEXT NOT NULL,
            full_name TEXT NOT NULL,
            token_hash TEXT NOT NULL UNIQUE,
            expires_at TIMESTAMPTZ NOT NULL,
            accepted_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            invited_by_user_id UUID REFERENCES catalog.users(id)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE catalog.email_outbox (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id UUID REFERENCES catalog.tenants(id) ON DELETE CASCADE,
            to_email TEXT NOT NULL,
            template TEXT NOT NULL,
            payload JSONB NOT NULL DEFAULT '{}',
            scheduled_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            sent_at TIMESTAMPTZ,
            attempts INTEGER NOT NULL DEFAULT 0,
            last_error TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        """
        CREATE TABLE catalog.consent_records (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id UUID NOT NULL REFERENCES catalog.tenants(id) ON DELETE CASCADE,
            user_id UUID REFERENCES catalog.users(id) ON DELETE SET NULL,
            policy_version TEXT NOT NULL,
            accept_privacy_policy BOOLEAN NOT NULL,
            accept_habeas_data BOOLEAN NOT NULL,
            ip_address TEXT,
            recorded_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        """
        CREATE TABLE catalog.platform_audit_events (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            occurred_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            event_type TEXT NOT NULL,
            actor_email TEXT,
            ip_address TEXT,
            tenant_id UUID REFERENCES catalog.tenants(id) ON DELETE SET NULL,
            payload JSONB NOT NULL DEFAULT '{}'
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS catalog.platform_audit_events")
    op.execute("DROP TABLE IF EXISTS catalog.consent_records")
    op.execute("DROP TABLE IF EXISTS catalog.email_outbox")
    op.execute("DROP TABLE IF EXISTS catalog.invites")
    op.execute("DROP TABLE IF EXISTS catalog.password_reset_tokens")
    op.execute("DROP TABLE IF EXISTS catalog.email_verify_tokens")
    op.execute("DROP INDEX IF EXISTS catalog.email_identities_lower_email_idx")
    op.execute("DROP TABLE IF EXISTS catalog.email_identities")
    op.execute("DROP TABLE IF EXISTS catalog.users")
    op.execute("DROP TABLE IF EXISTS catalog.tenants")
