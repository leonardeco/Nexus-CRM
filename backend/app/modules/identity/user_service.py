from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from redis.asyncio import Redis
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.modules.audit.service import AuditService
from app.modules.identity.auth_service import MFA_ROLES
from app.modules.identity.models import EmailIdentity, User
from app.modules.identity.session_service import SessionService
from app.modules.tenancy.models import Tenant

_VALID_ROLES = frozenset({"administrador", "gerente", "vendedor"})


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _last_admin() -> AppError:
    return AppError(
        409,
        "last_admin",
        "Último administrador",
        "No puedes dejar la empresa sin un administrador.",
    )


def _not_found() -> AppError:
    return AppError(
        404,
        "not_found",
        "No encontrado",
        "No encontrado.",
    )


def serialize_user(user: User, email: str) -> dict[str, Any]:
    return {
        "id": str(user.id),
        "email": email,
        "fullName": user.full_name,
        "role": user.role,
        "status": user.status,
        "mfaStatus": user.mfa_status,
    }


def serialize_tenant(tenant: Tenant) -> dict[str, Any]:
    return {
        "id": str(tenant.id),
        "slug": tenant.slug,
        "companyName": tenant.company_name,
        "plan": tenant.plan,
        "seatCap": tenant.seat_cap,
        "status": tenant.status,
    }


class UserService:
    def __init__(self, session: AsyncSession, redis: Redis) -> None:
        self._session = session
        self._sessions = SessionService(redis)
        self._audit = AuditService()

    async def list_users(self, actor: dict[str, Any]) -> list[dict[str, Any]]:
        tenant_id = UUID(str(actor["tenantId"]))
        rows = (
            await self._session.execute(
                select(User, EmailIdentity.email)
                .join(EmailIdentity, EmailIdentity.user_id == User.id)
                .where(User.tenant_id == tenant_id)
                .order_by(User.created_at)
            )
        ).all()
        return [serialize_user(user, email) for user, email in rows]

    async def deactivate(
        self, actor: dict[str, Any], user_id: UUID, *, ip: str
    ) -> dict[str, Any]:
        target, email, tenant = await self._load_tenant_user(actor, user_id)
        if target.status != "active":
            return serialize_user(target, email)
        if target.role == "administrador":
            if await self._active_admin_count(target.tenant_id) <= 1:
                raise _last_admin()
        target.status = "deactivated"
        target.deactivated_at = _now()
        await self._sessions.revoke_for_user(target.id)
        await self._audit.append(
            self._session,
            event_type="users.deactivated",
            actor_email=str(actor.get("email")),
            ip_address=ip,
            tenant_id=tenant.id,
            schema_name=tenant.schema_name,
            payload={"userId": str(target.id)},
        )
        await self._session.commit()
        return serialize_user(target, email)

    async def change_role(
        self, actor: dict[str, Any], user_id: UUID, role: str, *, ip: str
    ) -> dict[str, Any]:
        if role not in _VALID_ROLES:
            raise AppError(
                422,
                "validation_error",
                "Datos inválidos",
                "Revisa los campos enviados.",
            )
        target, email, tenant = await self._load_tenant_user(actor, user_id)
        if target.status != "active":
            raise _not_found()
        if (
            target.role == "administrador"
            and role != "administrador"
            and await self._active_admin_count(target.tenant_id) <= 1
        ):
            raise _last_admin()
        previous = target.role
        target.role = role
        if role in MFA_ROLES:
            target.mfa_status = "pending"
            await self._sessions.revoke_for_user(target.id)
        elif role == "vendedor":
            target.mfa_status = "not_required"
        await self._audit.append(
            self._session,
            event_type="users.role.changed",
            actor_email=str(actor.get("email")),
            ip_address=ip,
            tenant_id=tenant.id,
            schema_name=tenant.schema_name,
            payload={"userId": str(target.id), "from": previous, "to": role},
        )
        await self._session.commit()
        return serialize_user(target, email)

    async def get_tenant(self, actor: dict[str, Any]) -> dict[str, Any]:
        tenant = await self._session.get(Tenant, UUID(str(actor["tenantId"])))
        if tenant is None:
            raise _not_found()
        return serialize_tenant(tenant)

    async def patch_tenant(
        self,
        actor: dict[str, Any],
        *,
        company_name: str | None,
        slug: str | None,
        ip: str,
    ) -> dict[str, Any]:
        tenant = await self._session.get(Tenant, UUID(str(actor["tenantId"])))
        if tenant is None:
            raise _not_found()
        if company_name is not None:
            tenant.company_name = company_name
        if slug is not None and slug != tenant.slug:
            taken = await self._session.scalar(
                select(Tenant.id).where(Tenant.slug == slug, Tenant.id != tenant.id)
            )
            if taken is not None:
                raise AppError(
                    409,
                    "slug_taken",
                    "Identificador en uso",
                    "Ese identificador ya está en uso.",
                )
            tenant.slug = slug
        await self._session.commit()
        return serialize_tenant(tenant)

    async def _load_tenant_user(
        self, actor: dict[str, Any], user_id: UUID
    ) -> tuple[User, str, Tenant]:
        tenant_id = UUID(str(actor["tenantId"]))
        target = await self._session.get(User, user_id)
        if target is None or target.tenant_id != tenant_id:
            raise _not_found()
        identity = await self._session.scalar(
            select(EmailIdentity).where(EmailIdentity.user_id == target.id)
        )
        tenant = await self._session.get(Tenant, tenant_id)
        if identity is None or tenant is None:
            raise _not_found()
        return target, identity.email, tenant

    async def _active_admin_count(self, tenant_id: UUID) -> int:
        count = await self._session.scalar(
            select(func.count())
            .select_from(User)
            .where(
                User.tenant_id == tenant_id,
                User.role == "administrador",
                User.status == "active",
            )
        )
        return int(count or 0)
