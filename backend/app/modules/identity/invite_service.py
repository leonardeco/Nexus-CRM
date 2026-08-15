from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID, uuid4

from redis.asyncio import Redis
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.core.security import hash_token
from app.modules.audit.service import AuditService
from app.modules.emailing import outbox
from app.modules.identity.auth_service import (
    MFA_ROLES,
    build_principal,
    secrets_token,
)
from app.modules.identity.models import EmailIdentity, Invite, User
from app.modules.identity.password_service import PasswordService
from app.modules.identity.session_service import SessionService
from app.modules.tenancy.models import Tenant

_VALID_ROLES = frozenset({"administrador", "gerente", "vendedor"})


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _email_taken() -> AppError:
    return AppError(
        409,
        "email_taken",
        "Correo en uso",
        "Ese correo ya está registrado.",
    )


def _seat_cap_exceeded() -> AppError:
    return AppError(
        409,
        "seat_cap_exceeded",
        "Límite de usuarios",
        "Alcanzaste el máximo de usuarios de tu plan.",
    )


def _invalid_token() -> AppError:
    return AppError(
        400,
        "invalid_token",
        "Enlace inválido",
        "El enlace no es válido o expiró.",
    )


class InviteService:
    def __init__(self, session: AsyncSession, redis: Redis) -> None:
        self._session = session
        self._passwords = PasswordService()
        self._sessions = SessionService(redis)
        self._audit = AuditService()

    async def create(
        self,
        actor: dict[str, Any],
        email: str,
        role: str,
        full_name: str,
        *,
        ip: str,
    ) -> None:
        if role not in _VALID_ROLES:
            raise AppError(
                422,
                "validation_error",
                "Datos inválidos",
                "Revisa los campos enviados.",
            )
        tenant_id = UUID(str(actor["tenantId"]))
        email_norm = email.strip()
        tenant = await self._session.scalar(
            select(Tenant).where(Tenant.id == tenant_id).with_for_update()
        )
        if tenant is None:
            raise AppError(
                404,
                "not_found",
                "No encontrado",
                "No encontrado.",
            )
        existing = await self._session.scalar(
            select(EmailIdentity.id).where(
                func.lower(EmailIdentity.email) == email_norm.lower()
            )
        )
        if existing is not None:
            raise _email_taken()
        pending_same = await self._session.scalar(
            select(Invite.id).where(
                func.lower(Invite.email) == email_norm.lower(),
                Invite.accepted_at.is_(None),
                Invite.expires_at > _now(),
            )
        )
        if pending_same is not None:
            raise _email_taken()
        occupied = await self._occupied_seats(tenant_id)
        if occupied >= tenant.seat_cap:
            raise _seat_cap_exceeded()
        raw = secrets_token()
        invite = Invite(
            tenant_id=tenant_id,
            email=email_norm,
            role=role,
            full_name=full_name.strip(),
            token_hash=hash_token(raw),
            expires_at=_now() + timedelta(hours=72),
            invited_by_user_id=UUID(str(actor["userId"])),
        )
        self._session.add(invite)
        await outbox.enqueue(
            self._session,
            to_email=email_norm,
            template="invite",
            payload={"subject": "Invitación a NEXUS CRM"},
            tenant_id=tenant_id,
            raw_token=raw,
        )
        await self._audit.append(
            self._session,
            event_type="users.invite.created",
            actor_email=str(actor.get("email")),
            ip_address=ip,
            tenant_id=tenant_id,
            schema_name=tenant.schema_name,
            payload={"role": role},
        )
        await self._session.commit()

    async def accept(
        self, token: str, password: str, *, ip: str
    ) -> dict[str, Any]:
        self._passwords.validate_policy(password)
        digest = hash_token(token)
        invite = await self._session.scalar(
            select(Invite).where(Invite.token_hash == digest).with_for_update()
        )
        if (
            invite is None
            or invite.accepted_at is not None
            or invite.expires_at <= _now()
        ):
            raise _invalid_token()
        existing = await self._session.scalar(
            select(EmailIdentity.id).where(
                func.lower(EmailIdentity.email) == invite.email.lower()
            )
        )
        if existing is not None:
            raise _email_taken()
        tenant = await self._session.get(Tenant, invite.tenant_id)
        if tenant is None or tenant.status != "active":
            raise _invalid_token()
        user = User(
            id=uuid4(),
            tenant_id=invite.tenant_id,
            full_name=invite.full_name,
            role=invite.role,
            status="active",
            mfa_status="pending" if invite.role in MFA_ROLES else "not_required",
            password_hash=await self._passwords.hash(password),
            email_verified_at=_now(),
        )
        self._session.add(user)
        await self._session.flush()
        self._session.add(EmailIdentity(user_id=user.id, email=invite.email))
        try:
            await self._session.flush()
        except IntegrityError as exc:
            await self._session.rollback()
            raise _email_taken() from exc
        invite.accepted_at = _now()
        await self._audit.append(
            self._session,
            event_type="users.invite.accepted",
            actor_email=invite.email,
            ip_address=ip,
            tenant_id=tenant.id,
            schema_name=tenant.schema_name,
        )
        await self._session.commit()
        scope = "mfa_enroll_only" if user.role in MFA_ROLES else "full"
        principal = build_principal(user, tenant, invite.email, scope=scope)
        session_id = await self._sessions.create(principal, scope=scope)
        principal["sessionId"] = session_id
        return principal

    async def _occupied_seats(self, tenant_id: UUID) -> int:
        active = await self._session.scalar(
            select(func.count())
            .select_from(User)
            .where(User.tenant_id == tenant_id, User.status == "active")
        )
        pending = await self._session.scalar(
            select(func.count())
            .select_from(Invite)
            .where(
                Invite.tenant_id == tenant_id,
                Invite.accepted_at.is_(None),
                Invite.expires_at > _now(),
            )
        )
        return int(active or 0) + int(pending or 0)
