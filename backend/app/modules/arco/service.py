from typing import Any, Literal
from uuid import UUID, uuid4

from redis.asyncio import Redis
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.core.rate_limit import arco_rate_key, enforce_rate_limit
from app.db.identifiers import SCHEMA_NAME_RE
from app.db.search_path import set_search_path
from app.modules.audit.service import AuditService
from app.modules.tenancy.models import Tenant

ArcoType = Literal["acceso", "rectificacion", "cancelacion", "oposicion"]
_RETURNING = """
    id, request_type, source, status, requester_name, requester_email,
    details, response_text
"""


def _not_found() -> AppError:
    return AppError(
        404,
        "not_found",
        "No encontrado",
        "No encontrado.",
    )


def _serialize(row: Any) -> dict[str, Any]:
    mapping = dict(row)
    body: dict[str, Any] = {
        "id": str(mapping["id"]),
        "requestType": mapping["request_type"],
        "source": mapping["source"],
        "status": mapping["status"],
        "requesterName": mapping["requester_name"],
        "requesterEmail": mapping["requester_email"],
    }
    if mapping.get("details") is not None:
        body["details"] = mapping["details"]
    if mapping.get("response_text") is not None:
        body["responseText"] = mapping["response_text"]
    return body


class ArcoService:
    def __init__(self, session: AsyncSession, redis: Redis | None = None) -> None:
        self._session = session
        self._redis = redis
        self._audit = AuditService()

    async def submit_public(
        self,
        slug: str,
        *,
        requester_name: str,
        requester_email: str,
        request_type: ArcoType,
        details: str,
        ip: str,
    ) -> dict[str, Any]:
        if self._redis is None:
            raise AppError(
                503,
                "redis_unavailable",
                "Servicio no disponible",
                "Intenta de nuevo",
            )
        await enforce_rate_limit(
            self._redis,
            key=arco_rate_key(slug, ip),
            limit=10,
            window_seconds=900,
        )
        tenant = await self._active_by_slug(slug)
        row = await self._insert(
            tenant,
            request_type=request_type,
            source="public_form",
            requester_name=requester_name,
            requester_email=requester_email,
            details=details,
            created_by_user_id=None,
        )
        await self._audit.append(
            self._session,
            event_type="arco.created",
            actor_email=requester_email,
            ip_address=ip,
            tenant_id=tenant.id,
            schema_name=tenant.schema_name,
            payload={"source": "public_form", "requestType": request_type},
        )
        await self._session.commit()
        return _serialize(row)

    async def submit_self(
        self,
        actor: dict[str, Any],
        *,
        request_type: ArcoType,
        details: str,
        ip: str,
    ) -> dict[str, Any]:
        if actor.get("scope") != "full":
            raise AppError(
                403,
                "forbidden",
                "Acceso denegado",
                "No tienes permiso para esta acción.",
            )
        tenant = await self._tenant_for(actor)
        row = await self._insert(
            tenant,
            request_type=request_type,
            source="logged_in_self",
            requester_name=str(actor["fullName"]),
            requester_email=str(actor["email"]),
            details=details,
            created_by_user_id=UUID(str(actor["userId"])),
        )
        await self._audit.append(
            self._session,
            event_type="arco.created",
            actor_email=str(actor.get("email")),
            ip_address=ip,
            tenant_id=tenant.id,
            schema_name=tenant.schema_name,
            payload={"source": "logged_in_self", "requestType": request_type},
        )
        await self._session.commit()
        return _serialize(row)

    async def intake_manual(
        self,
        actor: dict[str, Any],
        *,
        request_type: ArcoType,
        requester_name: str,
        requester_email: str,
        details: str,
        ip: str,
    ) -> dict[str, Any]:
        tenant = await self._tenant_for(actor)
        row = await self._insert(
            tenant,
            request_type=request_type,
            source="manual_mail",
            requester_name=requester_name,
            requester_email=requester_email,
            details=details,
            created_by_user_id=UUID(str(actor["userId"])),
        )
        await self._audit.append(
            self._session,
            event_type="arco.created",
            actor_email=str(actor.get("email")),
            ip_address=ip,
            tenant_id=tenant.id,
            schema_name=tenant.schema_name,
            payload={"source": "manual_mail", "requestType": request_type},
        )
        await self._session.commit()
        return _serialize(row)

    async def list_inbox(self, actor: dict[str, Any]) -> list[dict[str, Any]]:
        tenant = await self._tenant_for(actor)
        await self._bind(tenant.schema_name)
        result = await self._session.execute(
            text(
                f"""
                SELECT {_RETURNING}
                FROM arco_requests
                ORDER BY created_at DESC, id DESC
                """
            )
        )
        return [_serialize(row) for row in result.mappings()]

    async def record_response(
        self,
        actor: dict[str, Any],
        request_id: UUID,
        *,
        response_text: str,
        ip: str,
    ) -> dict[str, Any]:
        tenant = await self._tenant_for(actor)
        current = await self._get(tenant.schema_name, request_id)
        if current["status"] == "closed":
            raise _not_found()
        await self._bind(tenant.schema_name)
        result = await self._session.execute(
            text(
                f"""
                UPDATE arco_requests
                SET status = 'responded',
                    response_text = :response_text,
                    responded_at = now()
                WHERE id = :id
                RETURNING {_RETURNING}
                """
            ),
            {"id": request_id, "response_text": response_text},
        )
        row = result.mappings().first()
        if row is None:
            raise _not_found()
        await self._audit.append(
            self._session,
            event_type="arco.responded",
            actor_email=str(actor.get("email")),
            ip_address=ip,
            tenant_id=tenant.id,
            schema_name=tenant.schema_name,
            payload={"arcoId": str(request_id)},
        )
        await self._session.commit()
        return _serialize(row)

    async def close(
        self,
        actor: dict[str, Any],
        request_id: UUID,
        *,
        ip: str,
    ) -> dict[str, Any]:
        tenant = await self._tenant_for(actor)
        await self._get(tenant.schema_name, request_id)
        await self._bind(tenant.schema_name)
        result = await self._session.execute(
            text(
                f"""
                UPDATE arco_requests
                SET status = 'closed',
                    closed_at = now()
                WHERE id = :id
                RETURNING {_RETURNING}
                """
            ),
            {"id": request_id},
        )
        row = result.mappings().first()
        if row is None:
            raise _not_found()
        await self._audit.append(
            self._session,
            event_type="arco.closed",
            actor_email=str(actor.get("email")),
            ip_address=ip,
            tenant_id=tenant.id,
            schema_name=tenant.schema_name,
            payload={"arcoId": str(request_id)},
        )
        await self._session.commit()
        return _serialize(row)

    async def _insert(
        self,
        tenant: Tenant,
        *,
        request_type: str,
        source: str,
        requester_name: str,
        requester_email: str,
        details: str,
        created_by_user_id: UUID | None,
    ) -> Any:
        await self._bind(tenant.schema_name)
        result = await self._session.execute(
            text(
                f"""
                INSERT INTO arco_requests (
                    id, request_type, source, status, requester_name,
                    requester_email, details, created_by_user_id
                )
                VALUES (
                    :id, :request_type, :source, 'open', :requester_name,
                    :requester_email, :details, :created_by_user_id
                )
                RETURNING {_RETURNING}
                """
            ),
            {
                "id": uuid4(),
                "request_type": request_type,
                "source": source,
                "requester_name": requester_name,
                "requester_email": requester_email,
                "details": details,
                "created_by_user_id": created_by_user_id,
            },
        )
        return result.mappings().one()

    async def _get(self, schema_name: str, request_id: UUID) -> dict[str, Any]:
        await self._bind(schema_name)
        row = (
            await self._session.execute(
                text(
                    f"""
                    SELECT {_RETURNING}
                    FROM arco_requests
                    WHERE id = :id
                    """
                ),
                {"id": request_id},
            )
        ).mappings().first()
        if row is None:
            raise _not_found()
        return dict(row)

    async def _active_by_slug(self, slug: str) -> Tenant:
        tenant = await self._session.scalar(select(Tenant).where(Tenant.slug == slug))
        if (
            tenant is None
            or tenant.status != "active"
            or SCHEMA_NAME_RE.match(tenant.schema_name) is None
        ):
            raise _not_found()
        return tenant

    async def _tenant_for(self, actor: dict[str, Any]) -> Tenant:
        tenant = await self._session.get(Tenant, UUID(str(actor["tenantId"])))
        if (
            tenant is None
            or tenant.status != "active"
            or SCHEMA_NAME_RE.match(tenant.schema_name) is None
        ):
            raise _not_found()
        return tenant

    async def _bind(self, schema_name: str) -> None:
        if SCHEMA_NAME_RE.match(schema_name) is None:
            raise _not_found()
        bind = await self._session.connection()
        await set_search_path(bind, schema_name)
