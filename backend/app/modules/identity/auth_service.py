from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID, uuid4

from redis.asyncio import Redis
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.errors import AppError
from app.core.rate_limit import (
    enforce_rate_limit,
    login_rate_key,
    mfa_account_rate_key,
    mfa_rate_key,
    password_reset_rate_key,
    redis_unavailable_error,
    resend_rate_key,
    signup_rate_key,
)
from app.core.security import hash_token
from app.db.identifiers import schema_name_for
from app.modules.audit.service import AuditService
from app.modules.consent.service import ConsentService
from app.modules.emailing import outbox
from app.modules.identity.mfa_service import MfaService
from app.modules.identity.models import (
    EmailIdentity,
    EmailVerifyToken,
    PasswordResetToken,
    User,
)
from app.modules.identity.password_service import PasswordService
from app.modules.identity.session_service import SessionService
from app.modules.tenancy.models import Tenant
from app.modules.tenancy.provisioner import TenantProvisioner

MFA_ROLES = frozenset({"administrador", "gerente"})
_MFA_ROLES = MFA_ROLES
_INVALID_CREDENTIALS = AppError(
    401,
    "invalid_credentials",
    "Credenciales inválidas",
    "Credenciales inválidas",
)
_MFA_INVALID = AppError(
    401,
    "mfa_invalid",
    "Código inválido",
    "El código de autenticación no es válido.",
)
_MFA_FAILURE_LIMIT = 5
_MFA_FAILURE_WINDOW = 300


@dataclass
class SignupCommand:
    company_name: str
    slug: str
    admin_full_name: str
    email: str
    password: str
    accept_privacy_policy: bool
    accept_habeas_data: bool
    policy_version: str


@dataclass
class LoginResult:
    status: str
    principal: dict[str, Any] | None = None
    mfa_challenge_id: str | None = None
    session_id: str | None = None


def _now() -> datetime:
    return datetime.now(timezone.utc)


def build_principal(
    user: User, tenant: Tenant, email: str, *, scope: str
) -> dict[str, Any]:
    return {
        "userId": str(user.id),
        "tenantId": str(tenant.id),
        "role": user.role,
        "mfaStatus": user.mfa_status,
        "scope": scope,
        "email": email,
        "fullName": user.full_name,
        "tenantSlug": tenant.slug,
    }


class AuthService:
    def __init__(self, session: AsyncSession, redis: Redis) -> None:
        self._session = session
        self._redis = redis
        self._passwords = PasswordService()
        self._sessions = SessionService(redis)
        self._mfa = MfaService()
        self._consent = ConsentService()
        self._audit = AuditService()

    async def signup(self, cmd: SignupCommand, *, ip: str, user_agent: str) -> None:
        await enforce_rate_limit(
            self._redis, key=signup_rate_key(ip), limit=10, window_seconds=3600
        )
        self._passwords.validate_policy(cmd.password)
        if cmd.policy_version != settings.current_policy_version:
            raise AppError(
                409,
                "policy_version_stale",
                "Política desactualizada",
                "Acepta la versión vigente de la política de privacidad.",
            )
        email = cmd.email.strip()
        existing = await self._identity_for_email(email)
        if existing is not None:
            return
        slug_taken = await self._session.scalar(
            select(Tenant.id).where(Tenant.slug == cmd.slug)
        )
        if slug_taken is not None:
            raise AppError(
                409,
                "slug_taken",
                "Identificador en uso",
                "Ese identificador ya está en uso.",
            )
        tenant_id = uuid4()
        user_id = uuid4()
        tenant = Tenant(
            id=tenant_id,
            slug=cmd.slug,
            company_name=cmd.company_name,
            schema_name=schema_name_for(tenant_id),
            plan="starter",
            seat_cap=2,
            status="pending_verification",
        )
        self._session.add(tenant)
        await self._session.flush()
        user = User(
            id=user_id,
            tenant_id=tenant_id,
            full_name=cmd.admin_full_name,
            role="administrador",
            status="active",
            mfa_status="pending",
            password_hash=await self._passwords.hash(cmd.password),
        )
        self._session.add(user)
        await self._session.flush()
        identity = EmailIdentity(user_id=user_id, email=email)
        self._session.add(identity)
        try:
            await self._session.flush()
        except IntegrityError:
            await self._session.rollback()
            return
        await self._consent.record(
            self._session,
            tenant_id=tenant_id,
            user_id=user_id,
            policy_version=cmd.policy_version,
            ip=ip,
            accept_privacy_policy=cmd.accept_privacy_policy,
            accept_habeas_data=cmd.accept_habeas_data,
        )
        raw_token = await self._issue_verify_token(user_id)
        await outbox.enqueue(
            self._session,
            to_email=email,
            template="verify_email",
            payload={"subject": "Verifica tu correo"},
            tenant_id=tenant_id,
            raw_token=raw_token,
        )
        await self._audit.append(
            self._session,
            event_type="tenant.signup",
            actor_email=email,
            ip_address=ip,
            tenant_id=tenant_id,
            payload={"userAgent": user_agent},
        )
        await self._audit.append(
            self._session,
            event_type="consent.recorded",
            actor_email=email,
            ip_address=ip,
            tenant_id=tenant_id,
            payload={"policyVersion": cmd.policy_version},
        )
        await self._session.commit()

    async def verify_email(self, token: str, *, ip: str) -> None:
        digest = hash_token(token)
        row = await self._session.scalar(
            select(EmailVerifyToken).where(EmailVerifyToken.token_hash == digest)
        )
        if row is None or row.consumed_at is not None or row.expires_at <= _now():
            raise AppError(
                400,
                "invalid_token",
                "Enlace inválido",
                "El enlace no es válido o expiró.",
            )
        user = await self._session.get(User, row.user_id)
        if user is None:
            raise AppError(
                400,
                "invalid_token",
                "Enlace inválido",
                "El enlace no es válido o expiró.",
            )
        tenant = await self._session.get(Tenant, user.tenant_id)
        if tenant is None:
            raise AppError(
                400,
                "invalid_token",
                "Enlace inválido",
                "El enlace no es válido o expiró.",
            )
        row.consumed_at = _now()
        user.email_verified_at = _now()
        if tenant.status != "active":
            tenant.status = "provisioning"
        identity = await self._session.scalar(
            select(EmailIdentity).where(EmailIdentity.user_id == user.id)
        )
        actor_email = identity.email if identity is not None else None
        await self._audit.append(
            self._session,
            event_type="auth.email.verified",
            actor_email=actor_email,
            ip_address=ip,
            tenant_id=tenant.id,
        )
        await self._session.commit()
        provisioner = TenantProvisioner(self._session)
        provisioned = await provisioner.provision(tenant.id)
        provisioned.status = "active"
        await self._session.commit()

    async def resend_verification(self, email: str, *, ip: str) -> None:
        await enforce_rate_limit(
            self._redis,
            key=resend_rate_key(email.lower()),
            limit=3,
            window_seconds=900,
        )
        loaded = await self._user_tenant_email(email)
        if loaded is None:
            return
        user, tenant, identity = loaded
        if tenant.status != "pending_verification":
            return
        raw_token = await self._issue_verify_token(user.id)
        await outbox.enqueue(
            self._session,
            to_email=identity.email,
            template="verify_email",
            payload={"subject": "Verifica tu correo"},
            tenant_id=tenant.id,
            raw_token=raw_token,
        )
        await self._session.commit()

    async def login(self, email: str, password: str, *, ip: str) -> LoginResult:
        try:
            await self._redis.ping()
        except Exception as exc:
            raise redis_unavailable_error() from exc
        key = login_rate_key(email.lower(), ip)
        try:
            raw_count = await self._redis.get(key)
        except Exception as exc:
            raise redis_unavailable_error() from exc
        if raw_count is not None and int(raw_count) >= 5:
            raise AppError(
                429,
                "rate_limited",
                "Demasiados intentos",
                "Intenta de nuevo más tarde.",
            )
        loaded = await self._user_tenant_email(email)
        if loaded is None:
            await self._fail_login(email, ip, key)
        user, tenant, identity = loaded  # type: ignore[misc]
        if user.status != "active" or not user.password_hash:
            await self._fail_login(email, ip, key)
        if not await self._passwords.verify(password, user.password_hash or ""):
            await self._fail_login(email, ip, key)
        if user.email_verified_at is None:
            raise AppError(
                403,
                "email_not_verified",
                "Correo no verificado",
                "Debes verificar tu correo.",
            )
        if tenant.status != "active":
            raise AppError(
                403,
                "tenant_not_ready",
                "Empresa no lista",
                "La empresa aún no está lista.",
            )
        if user.role in _MFA_ROLES and user.mfa_status == "pending":
            principal = build_principal(
                user, tenant, identity.email, scope="mfa_enroll_only"
            )
            session_id = await self._sessions.create(
                principal, scope="mfa_enroll_only"
            )
            return LoginResult(
                status="mfa_enrollment_required",
                principal=principal,
                session_id=session_id,
            )
        if user.role in _MFA_ROLES and user.mfa_status == "enrolled":
            await self._reject_if_mfa_locked(user.id)
            challenge_id = await self._sessions.create_mfa_challenge(user.id)
            return LoginResult(status="mfa_required", mfa_challenge_id=challenge_id)
        principal = build_principal(user, tenant, identity.email, scope="full")
        session_id = await self._sessions.create(principal, scope="full")
        await self._audit.append(
            self._session,
            event_type="auth.login.success",
            actor_email=identity.email,
            ip_address=ip,
            tenant_id=tenant.id,
            schema_name=tenant.schema_name if tenant.status == "active" else None,
        )
        await self._session.commit()
        return LoginResult(
            status="authenticated", principal=principal, session_id=session_id
        )

    async def complete_mfa(
        self, challenge_id: str, code: str, *, ip: str
    ) -> dict[str, Any]:
        challenge = await self._sessions.get_mfa_challenge(challenge_id)
        if challenge is None:
            raise _MFA_INVALID
        user_id = UUID(str(challenge["userId"]))
        user = await self._session.scalar(
            select(User).where(User.id == user_id).with_for_update()
        )
        if user is None:
            raise _MFA_INVALID
        try:
            await self._mfa.verify_login(user, code)
        except AppError:
            tenant, identity = await self._tenant_and_email(user)
            await self._audit.append(
                self._session,
                event_type="auth.login.failure",
                actor_email=identity.email,
                ip_address=ip,
                tenant_id=tenant.id,
            )
            await self._session.commit()
            try:
                await enforce_rate_limit(
                    self._redis,
                    key=mfa_account_rate_key(str(user_id)),
                    limit=_MFA_FAILURE_LIMIT,
                    window_seconds=_MFA_FAILURE_WINDOW,
                )
                failures = await enforce_rate_limit(
                    self._redis,
                    key=mfa_rate_key(challenge_id, str(user_id)),
                    limit=_MFA_FAILURE_LIMIT,
                    window_seconds=_MFA_FAILURE_WINDOW,
                )
            except AppError:
                await self._sessions.delete_mfa_challenge(challenge_id)
                raise
            if failures >= _MFA_FAILURE_LIMIT:
                await self._sessions.delete_mfa_challenge(challenge_id)
            raise
        tenant, identity = await self._tenant_and_email(user)
        principal = build_principal(user, tenant, identity.email, scope="full")
        session_id = await self._sessions.create(principal, scope="full")
        await self._sessions.delete_mfa_challenge(challenge_id)
        await self._audit.append(
            self._session,
            event_type="auth.login.success",
            actor_email=identity.email,
            ip_address=ip,
            tenant_id=tenant.id,
            schema_name=tenant.schema_name,
        )
        await self._session.commit()
        principal["sessionId"] = session_id
        return principal

    async def start_totp_enroll(self, user_id: UUID, email: str) -> str:
        user = await self._session.get(User, user_id)
        if user is None or user.mfa_status != "pending":
            raise AppError(
                403,
                "forbidden",
                "Acceso denegado",
                "No puedes enrolar MFA en este momento.",
            )
        otpauth_url, encrypted = self._mfa.start_enroll(email)
        user.totp_secret_encrypted = encrypted
        await self._session.commit()
        return otpauth_url

    async def confirm_totp_enroll(
        self, user_id: UUID, code: str, *, ip: str
    ) -> tuple[list[str], str, dict[str, Any]]:
        user = await self._session.scalar(
            select(User).where(User.id == user_id).with_for_update()
        )
        if user is None or user.mfa_status != "pending":
            raise AppError(
                403,
                "forbidden",
                "Acceso denegado",
                "No puedes enrolar MFA en este momento.",
            )
        codes = await self._mfa.enroll(user, code)
        tenant, identity = await self._tenant_and_email(user)
        await self._audit.append(
            self._session,
            event_type="auth.mfa.enrolled",
            actor_email=identity.email,
            ip_address=ip,
            tenant_id=tenant.id,
            schema_name=tenant.schema_name,
        )
        principal = build_principal(user, tenant, identity.email, scope="full")
        session_id = await self._sessions.create(principal, scope="full")
        await self._audit.append(
            self._session,
            event_type="auth.login.success",
            actor_email=identity.email,
            ip_address=ip,
            tenant_id=tenant.id,
            schema_name=tenant.schema_name,
        )
        await self._session.commit()
        return codes, session_id, principal

    async def request_password_reset(self, email: str, *, ip: str) -> None:
        await enforce_rate_limit(
            self._redis,
            key=password_reset_rate_key(email.lower()),
            limit=3,
            window_seconds=900,
        )
        loaded = await self._user_tenant_email(email)
        if loaded is None:
            return
        user, tenant, identity = loaded
        raw = secrets_token()
        row = PasswordResetToken(
            user_id=user.id,
            token_hash=hash_token(raw),
            expires_at=_now() + timedelta(hours=1),
        )
        self._session.add(row)
        await outbox.enqueue(
            self._session,
            to_email=identity.email,
            template="password_reset",
            payload={"subject": "Restablece tu contraseña"},
            tenant_id=tenant.id,
            raw_token=raw,
        )
        await self._session.commit()

    async def confirm_password_reset(self, token: str, password: str, *, ip: str) -> None:
        self._passwords.validate_policy(password)
        digest = hash_token(token)
        row = await self._session.scalar(
            select(PasswordResetToken).where(PasswordResetToken.token_hash == digest)
        )
        if row is None or row.consumed_at is not None or row.expires_at <= _now():
            raise AppError(
                400,
                "invalid_token",
                "Enlace inválido",
                "El enlace no es válido o expiró.",
            )
        user = await self._session.get(User, row.user_id)
        if user is None:
            raise AppError(
                400,
                "invalid_token",
                "Enlace inválido",
                "El enlace no es válido o expiró.",
            )
        await self._session.execute(
            update(PasswordResetToken)
            .where(
                PasswordResetToken.user_id == user.id,
                PasswordResetToken.consumed_at.is_(None),
            )
            .values(consumed_at=_now())
        )
        user.password_hash = await self._passwords.hash(password)
        await self._sessions.revoke_for_user(user.id)
        identity = await self._session.scalar(
            select(EmailIdentity).where(EmailIdentity.user_id == user.id)
        )
        await self._audit.append(
            self._session,
            event_type="auth.password.reset",
            actor_email=identity.email if identity is not None else None,
            ip_address=ip,
            tenant_id=user.tenant_id,
        )
        await self._session.commit()

    async def logout(self, session_id: str) -> None:
        await self._sessions.delete(session_id)

    async def load_session(self, session_id: str) -> dict[str, Any] | None:
        return await self._sessions.get(session_id)

    async def _reject_if_mfa_locked(self, user_id: UUID) -> None:
        try:
            raw_count = await self._redis.get(mfa_account_rate_key(str(user_id)))
        except Exception as exc:
            raise redis_unavailable_error() from exc
        if raw_count is not None and int(raw_count) >= _MFA_FAILURE_LIMIT:
            raise AppError(
                429,
                "rate_limited",
                "Demasiados intentos",
                "Intenta de nuevo más tarde.",
            )

    async def _fail_login(self, email: str, ip: str, key: str) -> None:
        await self._audit.append(
            self._session,
            event_type="auth.login.failure",
            actor_email=email,
            ip_address=ip,
        )
        await self._session.commit()
        await enforce_rate_limit(self._redis, key=key, limit=5, window_seconds=900)
        raise _INVALID_CREDENTIALS

    async def _issue_verify_token(self, user_id: UUID) -> str:
        raw = secrets_token()
        self._session.add(
            EmailVerifyToken(
                user_id=user_id,
                token_hash=hash_token(raw),
                expires_at=_now() + timedelta(hours=24),
            )
        )
        return raw

    async def _identity_for_email(self, email: str) -> EmailIdentity | None:
        return await self._session.scalar(
            select(EmailIdentity).where(func.lower(EmailIdentity.email) == email.lower())
        )

    async def _user_tenant_email(
        self, email: str
    ) -> tuple[User, Tenant, EmailIdentity] | None:
        stmt = (
            select(User, Tenant, EmailIdentity)
            .join(EmailIdentity, EmailIdentity.user_id == User.id)
            .join(Tenant, Tenant.id == User.tenant_id)
            .where(func.lower(EmailIdentity.email) == email.lower())
        )
        row = (await self._session.execute(stmt)).first()
        if row is None:
            return None
        return row[0], row[1], row[2]

    async def _tenant_and_email(self, user: User) -> tuple[Tenant, EmailIdentity]:
        tenant = await self._session.get(Tenant, user.tenant_id)
        identity = await self._session.scalar(
            select(EmailIdentity).where(EmailIdentity.user_id == user.id)
        )
        if tenant is None or identity is None:
            raise AppError(
                401,
                "invalid_credentials",
                "Credenciales inválidas",
                "Credenciales inválidas",
            )
        return tenant, identity


def secrets_token() -> str:
    import secrets

    return secrets.token_urlsafe(32)
