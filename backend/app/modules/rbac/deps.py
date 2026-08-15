from collections.abc import AsyncIterator, Callable, Coroutine
from typing import Annotated, Any
from uuid import UUID

from fastapi import Depends, Request
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.errors import AppError
from app.db.engine import get_session
from app.modules.identity.auth_service import AuthService, MFA_ROLES, build_principal
from app.modules.identity.models import EmailIdentity, User
from app.modules.rbac.matrix import has_permission
from app.modules.rbac.permissions import Permission
from app.modules.tenancy.models import Tenant


def forbidden() -> AppError:
    return AppError(
        403,
        "forbidden",
        "Acceso denegado",
        "No tienes permiso para esta acción.",
    )


def _unauthenticated() -> AppError:
    return AppError(
        401,
        "invalid_credentials",
        "Credenciales inválidas",
        "Credenciales inválidas",
    )


async def get_redis() -> AsyncIterator[Redis]:
    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    try:
        yield redis
    finally:
        await redis.aclose()


async def require_principal(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
    redis: Annotated[Redis, Depends(get_redis)],
) -> dict[str, Any]:
    token = request.cookies.get(settings.session_cookie_name)
    if not token:
        raise _unauthenticated()
    auth = AuthService(session, redis)
    stored = await auth.load_session(token)
    if stored is None:
        raise _unauthenticated()
    user = await session.get(User, UUID(str(stored["userId"])))
    if user is None or user.status != "active":
        await auth.logout(token)
        raise _unauthenticated()
    tenant = await session.get(Tenant, user.tenant_id)
    identity = await session.scalar(
        select(EmailIdentity).where(EmailIdentity.user_id == user.id)
    )
    if tenant is None or identity is None:
        await auth.logout(token)
        raise _unauthenticated()
    scope = str(stored.get("scope") or "full")
    if user.role in MFA_ROLES and user.mfa_status == "pending":
        scope = "mfa_enroll_only"
    principal = build_principal(user, tenant, identity.email, scope=scope)
    request.state.session_id = token
    return principal


def require_permission(
    permission: Permission,
) -> Callable[..., Coroutine[Any, Any, dict[str, Any]]]:
    async def _check(
        principal: Annotated[dict[str, Any], Depends(require_principal)],
    ) -> dict[str, Any]:
        if principal.get("scope") != "full":
            raise forbidden()
        if not has_permission(str(principal["role"]), permission):
            raise forbidden()
        return principal

    return _check
