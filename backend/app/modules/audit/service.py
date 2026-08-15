from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.identifiers import SCHEMA_NAME_RE
from app.db.search_path import set_search_path


def _iso(value: datetime) -> str:
    if value.tzinfo is None:
        return value.isoformat() + "Z"
    return value.isoformat().replace("+00:00", "Z")


class AuditService:
    async def append(
        self,
        session: AsyncSession,
        *,
        event_type: str,
        actor_email: str | None,
        ip_address: str | None,
        tenant_id: UUID | None = None,
        payload: dict[str, Any] | None = None,
        schema_name: str | None = None,
    ) -> UUID:
        import json

        event_id = uuid4()
        await session.execute(
            text(
                """
                INSERT INTO catalog.platform_audit_events
                    (id, event_type, actor_email, ip_address, tenant_id, payload)
                VALUES
                    (:id, :event_type, :actor_email, :ip_address, :tenant_id,
                     CAST(:payload AS jsonb))
                """
            ),
            {
                "id": event_id,
                "event_type": event_type,
                "actor_email": actor_email,
                "ip_address": ip_address,
                "tenant_id": tenant_id,
                "payload": json.dumps(payload or {}),
            },
        )
        if schema_name and SCHEMA_NAME_RE.match(schema_name):
            bind = await session.connection()
            await set_search_path(bind, schema_name)
            await session.execute(
                text(
                    """
                    INSERT INTO audit_events
                        (id, event_type, actor_email, ip_address, payload)
                    VALUES
                        (:id, :event_type, :actor_email, :ip_address,
                         CAST(:payload AS jsonb))
                    """
                ),
                {
                    "id": event_id,
                    "event_type": event_type,
                    "actor_email": actor_email,
                    "ip_address": ip_address,
                    "payload": json.dumps(payload or {}),
                },
            )
        return event_id

    async def list(
        self,
        session: AsyncSession,
        *,
        tenant_id: UUID,
        cursor_id: UUID | None = None,
        limit: int = 50,
    ) -> dict[str, Any]:
        result = await session.execute(
            text(
                """
                SELECT id, occurred_at, event_type, actor_email, ip_address
                FROM catalog.platform_audit_events
                WHERE (
                    tenant_id = :tenant_id
                    OR (
                        tenant_id IS NULL
                        AND event_type = 'auth.login.failure'
                        AND lower(actor_email) IN (
                            SELECT lower(ei.email)
                            FROM catalog.email_identities ei
                            JOIN catalog.users u ON u.id = ei.user_id
                            WHERE u.tenant_id = :tenant_id
                        )
                    )
                )
                AND (
                    CAST(:cursor_id AS uuid) IS NULL
                    OR (occurred_at, id) < (
                        SELECT e.occurred_at, e.id
                        FROM catalog.platform_audit_events e
                        WHERE e.id = CAST(:cursor_id AS uuid)
                          AND (
                            e.tenant_id = :tenant_id
                            OR (
                                e.tenant_id IS NULL
                                AND e.event_type = 'auth.login.failure'
                                AND lower(e.actor_email) IN (
                                    SELECT lower(ei.email)
                                    FROM catalog.email_identities ei
                                    JOIN catalog.users u ON u.id = ei.user_id
                                    WHERE u.tenant_id = :tenant_id
                                )
                            )
                        )
                    )
                )
                ORDER BY occurred_at DESC, id DESC
                LIMIT :limit
                """
            ),
            {
                "tenant_id": tenant_id,
                "cursor_id": cursor_id,
                "limit": limit + 1,
            },
        )
        rows = list(result.mappings())
        next_cursor = None
        if len(rows) > limit:
            rows = rows[:limit]
            next_cursor = str(rows[-1]["id"])
        items = [
            {
                "id": str(row["id"]),
                "occurredAt": _iso(row["occurred_at"]),
                "eventType": row["event_type"],
                "actorEmail": row["actor_email"],
                "ipAddress": row["ip_address"],
            }
            for row in rows
        ]
        page: dict[str, Any] = {"items": items}
        if next_cursor is not None:
            page["nextCursor"] = next_cursor
        return page
