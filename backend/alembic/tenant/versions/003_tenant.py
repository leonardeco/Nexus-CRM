"""sales pipeline: pipelines, stages, deals, deal_stage_events

Revision ID: 003_tenant
Revises: 002_tenant
"""

from alembic import op

revision = "003_tenant"
down_revision = "002_tenant"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE pipelines (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            name TEXT NOT NULL,
            is_default BOOLEAN NOT NULL DEFAULT false,
            archived_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX pipelines_one_default_idx
            ON pipelines (is_default) WHERE is_default AND archived_at IS NULL
        """
    )
    op.execute(
        """
        CREATE TABLE stages (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            pipeline_id UUID NOT NULL REFERENCES pipelines(id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            position INTEGER NOT NULL,
            probability INTEGER NOT NULL DEFAULT 0
                CHECK (probability BETWEEN 0 AND 100),
            rotting_days INTEGER CHECK (rotting_days IS NULL OR rotting_days > 0),
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX stages_pipeline_idx ON stages (pipeline_id, position)")
    op.execute(
        """
        CREATE TABLE deals (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            pipeline_id UUID NOT NULL REFERENCES pipelines(id),
            stage_id UUID NOT NULL REFERENCES stages(id),
            name TEXT NOT NULL,
            value NUMERIC(14,2) NOT NULL DEFAULT 0 CHECK (value >= 0),
            currency TEXT NOT NULL DEFAULT 'COP',
            contact_id UUID REFERENCES contacts(id) ON DELETE SET NULL,
            account_id UUID REFERENCES accounts(id) ON DELETE SET NULL,
            owner_user_id UUID,
            close_date DATE,
            probability INTEGER
                CHECK (probability IS NULL OR probability BETWEEN 0 AND 100),
            status TEXT NOT NULL DEFAULT 'open'
                CHECK (status IN ('open','won','lost')),
            lost_reason TEXT,
            stage_changed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            archived_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX deals_pipeline_idx ON deals (pipeline_id)")
    op.execute("CREATE INDEX deals_stage_idx ON deals (stage_id)")
    op.execute(
        "CREATE INDEX deals_active_idx ON deals (archived_at) "
        "WHERE archived_at IS NULL"
    )
    op.execute("CREATE INDEX deals_status_idx ON deals (status)")
    op.execute(
        """
        CREATE TABLE deal_stage_events (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            deal_id UUID NOT NULL REFERENCES deals(id) ON DELETE CASCADE,
            from_stage_id UUID,
            to_stage_id UUID NOT NULL,
            reason TEXT,
            actor_email TEXT,
            occurred_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        "CREATE INDEX deal_stage_events_deal_idx "
        "ON deal_stage_events (deal_id, occurred_at)"
    )
    op.execute(
        """
        WITH p AS (
            INSERT INTO pipelines (name, is_default)
            VALUES ('Ventas', true) RETURNING id
        )
        INSERT INTO stages (pipeline_id, name, position, probability, rotting_days)
        SELECT p.id, s.name, s.position, s.prob, s.rot FROM p,
            (VALUES
                ('Prospecto', 1, 10, 14),
                ('Calificado', 2, 30, 14),
                ('Propuesta', 3, 60, 10),
                ('Negociación', 4, 80, 7),
                ('Cierre', 5, 95, 7)
            ) AS s(name, position, prob, rot)
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS deal_stage_events")
    op.execute("DROP TABLE IF EXISTS deals")
    op.execute("DROP TABLE IF EXISTS stages")
    op.execute("DROP TABLE IF EXISTS pipelines")
