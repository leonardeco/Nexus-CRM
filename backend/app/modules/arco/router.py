from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from pydantic.alias_generators import to_camel
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.http import client_ip
from app.db.engine import get_session
from app.modules.arco.service import ArcoService
from app.modules.rbac.deps import get_redis, require_permission, require_principal
from app.modules.rbac.permissions import Permission

router = APIRouter(prefix="/api/v1")

ArcoType = Literal["acceso", "rectificacion", "cancelacion", "oposicion"]


class ApiModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class PublicArcoRequest(ApiModel):
    requester_name: str
    requester_email: EmailStr
    request_type: ArcoType
    details: str


class SelfArcoRequest(ApiModel):
    request_type: ArcoType
    details: str


class ManualArcoRequest(ApiModel):
    request_type: ArcoType
    requester_name: str
    requester_email: EmailStr
    details: str


class ArcoResponseRequest(ApiModel):
    response_text: str = Field(min_length=1)


class ArcoCloseRequest(ApiModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        extra="forbid",
    )


def _arco(session: AsyncSession, redis: Redis | None = None) -> ArcoService:
    return ArcoService(session, redis)


@router.post("/public/tenants/{slug}/arco-requests", status_code=201)
async def submit_public_arco(
    slug: str,
    payload: PublicArcoRequest,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
    redis: Annotated[Redis, Depends(get_redis)],
) -> dict[str, Any]:
    return await _arco(session, redis).submit_public(
        slug,
        requester_name=payload.requester_name,
        requester_email=str(payload.requester_email),
        request_type=payload.request_type,
        details=payload.details,
        ip=client_ip(request),
    )


@router.post("/me/arco-requests", status_code=201)
async def submit_self_arco(
    payload: SelfArcoRequest,
    request: Request,
    principal: Annotated[dict[str, Any], Depends(require_principal)],
    session: Annotated[AsyncSession, Depends(get_session)],
    redis: Annotated[Redis, Depends(get_redis)],
) -> dict[str, Any]:
    return await _arco(session, redis).submit_self(
        principal,
        request_type=payload.request_type,
        details=payload.details,
        ip=client_ip(request),
    )


@router.get("/arco-requests")
async def list_arco(
    principal: Annotated[
        dict[str, Any], Depends(require_permission(Permission.ARCO_INBOX_READ))
    ],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[dict[str, Any]]:
    return await _arco(session).list_inbox(principal)


@router.post("/arco-requests", status_code=201)
async def intake_manual_arco(
    payload: ManualArcoRequest,
    request: Request,
    principal: Annotated[
        dict[str, Any], Depends(require_permission(Permission.ARCO_INBOX_WRITE))
    ],
    session: Annotated[AsyncSession, Depends(get_session)],
    redis: Annotated[Redis, Depends(get_redis)],
) -> dict[str, Any]:
    return await _arco(session, redis).intake_manual(
        principal,
        request_type=payload.request_type,
        requester_name=payload.requester_name,
        requester_email=str(payload.requester_email),
        details=payload.details,
        ip=client_ip(request),
    )


@router.post("/arco-requests/{request_id}/response")
async def respond_arco(
    request_id: UUID,
    payload: ArcoResponseRequest,
    request: Request,
    principal: Annotated[
        dict[str, Any], Depends(require_permission(Permission.ARCO_INBOX_WRITE))
    ],
    session: Annotated[AsyncSession, Depends(get_session)],
    redis: Annotated[Redis, Depends(get_redis)],
) -> dict[str, Any]:
    return await _arco(session, redis).record_response(
        principal,
        request_id,
        response_text=payload.response_text,
        ip=client_ip(request),
    )


@router.post("/arco-requests/{request_id}/closure")
async def close_arco(
    request_id: UUID,
    payload: ArcoCloseRequest,
    request: Request,
    principal: Annotated[
        dict[str, Any], Depends(require_permission(Permission.ARCO_INBOX_WRITE))
    ],
    session: Annotated[AsyncSession, Depends(get_session)],
    redis: Annotated[Redis, Depends(get_redis)],
) -> dict[str, Any]:
    return await _arco(session, redis).close(
        principal, request_id, ip=client_ip(request)
    )
