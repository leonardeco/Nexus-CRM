from collections.abc import AsyncIterator
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from pydantic.alias_generators import to_camel
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.errors import AppError
from app.db.engine import get_session
from app.modules.identity.auth_service import AuthService, SignupCommand

router = APIRouter(prefix="/api/v1")


class ApiModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class SignupRequest(ApiModel):
    company_name: str
    slug: str = Field(pattern=r"^[a-z0-9-]{3,63}$")
    admin_full_name: str
    email: EmailStr
    password: str = Field(min_length=10)
    accept_privacy_policy: Literal[True]
    accept_habeas_data: Literal[True]
    policy_version: str


class TokenRequest(ApiModel):
    token: str


class ResendRequest(ApiModel):
    email: EmailStr


class LoginRequest(ApiModel):
    email: EmailStr
    password: str


class CompleteMfaRequest(ApiModel):
    challenge_id: str
    code: str


class PasswordResetRequest(ApiModel):
    email: EmailStr


class PasswordResetConfirmRequest(ApiModel):
    token: str
    password: str = Field(min_length=10)


class ConfirmTotpRequest(ApiModel):
    code: str
    backup_codes_saved: Literal[True]


async def get_redis() -> AsyncIterator[Redis]:
    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    try:
        yield redis
    finally:
        await redis.aclose()


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",", 1)[0].strip()
    if request.client is not None:
        return request.client.host
    return "0.0.0.0"


def _auth(session: AsyncSession, redis: Redis) -> AuthService:
    return AuthService(session, redis)


async def require_principal(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
    redis: Annotated[Redis, Depends(get_redis)],
) -> dict[str, Any]:
    token = request.cookies.get(settings.session_cookie_name)
    if not token:
        raise AppError(
            401,
            "invalid_credentials",
            "Credenciales inválidas",
            "Credenciales inválidas",
        )
    principal = await _auth(session, redis).load_session(token)
    if principal is None:
        raise AppError(
            401,
            "invalid_credentials",
            "Credenciales inválidas",
            "Credenciales inválidas",
        )
    request.state.session_id = token
    return principal


def _set_session_cookie(response: Response, session_id: str) -> None:
    response.set_cookie(
        key=settings.session_cookie_name,
        value=session_id,
        httponly=True,
        samesite="lax",
        path="/",
        max_age=settings.session_ttl_seconds,
        secure=False,
    )


@router.post("/public/signups", status_code=202)
async def create_signup(
    payload: SignupRequest,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
    redis: Annotated[Redis, Depends(get_redis)],
) -> Response:
    await _auth(session, redis).signup(
        SignupCommand(
            company_name=payload.company_name,
            slug=payload.slug,
            admin_full_name=payload.admin_full_name,
            email=str(payload.email),
            password=payload.password,
            accept_privacy_policy=bool(payload.accept_privacy_policy),
            accept_habeas_data=bool(payload.accept_habeas_data),
            policy_version=payload.policy_version,
        ),
        ip=_client_ip(request),
        user_agent=request.headers.get("User-Agent", ""),
    )
    return Response(status_code=202)


@router.post("/public/email-verifications", status_code=204)
async def verify_email(
    payload: TokenRequest,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
    redis: Annotated[Redis, Depends(get_redis)],
) -> Response:
    await _auth(session, redis).verify_email(payload.token, ip=_client_ip(request))
    return Response(status_code=204)


@router.post("/public/email-verifications/resend", status_code=202)
async def resend_verification(
    payload: ResendRequest,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
    redis: Annotated[Redis, Depends(get_redis)],
) -> Response:
    await _auth(session, redis).resend_verification(
        str(payload.email), ip=_client_ip(request)
    )
    return Response(status_code=202)


@router.post("/public/sessions")
async def create_session(
    payload: LoginRequest,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
    redis: Annotated[Redis, Depends(get_redis)],
) -> JSONResponse:
    result = await _auth(session, redis).login(
        str(payload.email), payload.password, ip=_client_ip(request)
    )
    body: dict[str, Any] = {"status": result.status}
    if result.mfa_challenge_id is not None:
        body["mfaChallengeId"] = result.mfa_challenge_id
    if result.principal is not None:
        body["principal"] = result.principal
    response = JSONResponse(content=body)
    if result.session_id is not None:
        _set_session_cookie(response, result.session_id)
        if result.status == "mfa_enrollment_required":
            response.set_cookie(
                key="nexus_preauth",
                value=result.session_id,
                httponly=True,
                samesite="lax",
                path="/",
                max_age=600,
                secure=False,
            )
    return response


@router.post("/public/sessions/mfa")
async def complete_mfa(
    payload: CompleteMfaRequest,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
    redis: Annotated[Redis, Depends(get_redis)],
) -> JSONResponse:
    principal = await _auth(session, redis).complete_mfa(
        payload.challenge_id, payload.code, ip=_client_ip(request)
    )
    session_id = str(principal.pop("sessionId"))
    response = JSONResponse(content=principal)
    _set_session_cookie(response, session_id)
    return response


@router.delete("/sessions/current", status_code=204)
async def logout(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
    redis: Annotated[Redis, Depends(get_redis)],
) -> Response:
    token = request.cookies.get(settings.session_cookie_name)
    if token:
        await _auth(session, redis).logout(token)
    response = Response(status_code=204)
    response.delete_cookie(settings.session_cookie_name, path="/")
    response.delete_cookie("nexus_preauth", path="/")
    return response


@router.post("/public/password-resets", status_code=202)
async def request_password_reset(
    payload: PasswordResetRequest,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
    redis: Annotated[Redis, Depends(get_redis)],
) -> Response:
    await _auth(session, redis).request_password_reset(
        str(payload.email), ip=_client_ip(request)
    )
    return Response(status_code=202)


@router.post("/public/password-resets/confirm", status_code=204)
async def confirm_password_reset(
    payload: PasswordResetConfirmRequest,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
    redis: Annotated[Redis, Depends(get_redis)],
) -> Response:
    await _auth(session, redis).confirm_password_reset(
        payload.token, payload.password, ip=_client_ip(request)
    )
    return Response(status_code=204)


@router.get("/me")
async def get_me(
    principal: Annotated[dict[str, Any], Depends(require_principal)],
) -> dict[str, Any]:
    return {
        key: principal[key]
        for key in (
            "userId",
            "tenantId",
            "role",
            "mfaStatus",
            "scope",
            "email",
            "fullName",
            "tenantSlug",
        )
        if key in principal
    }


@router.post("/me/mfa/totp")
async def start_totp_enroll(
    principal: Annotated[dict[str, Any], Depends(require_principal)],
    session: Annotated[AsyncSession, Depends(get_session)],
    redis: Annotated[Redis, Depends(get_redis)],
) -> dict[str, str]:
    if principal.get("scope") not in {"full", "mfa_enroll_only"}:
        raise AppError(
            401,
            "invalid_credentials",
            "Credenciales inválidas",
            "Credenciales inválidas",
        )
    otpauth_url = await _auth(session, redis).start_totp_enroll(
        UUID(str(principal["userId"])),
        str(principal["email"]),
    )
    return {"otpauthUrl": otpauth_url}


@router.post("/me/mfa/totp/confirm")
async def confirm_totp_enroll(
    payload: ConfirmTotpRequest,
    request: Request,
    principal: Annotated[dict[str, Any], Depends(require_principal)],
    session: Annotated[AsyncSession, Depends(get_session)],
    redis: Annotated[Redis, Depends(get_redis)],
) -> JSONResponse:
    codes, session_id, _updated = await _auth(session, redis).confirm_totp_enroll(
        UUID(str(principal["userId"])),
        payload.code,
        ip=_client_ip(request),
    )
    response = JSONResponse(content={"backupCodes": codes})
    _set_session_cookie(response, session_id)
    return response
