from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.identifiers import SCHEMA_NAME_RE
from app.db.search_path import set_search_path


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
