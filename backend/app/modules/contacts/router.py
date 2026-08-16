from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.http import client_ip
from app.db.engine import get_session
from app.modules.contacts.service import ContactsService
from app.modules.rbac.deps import require_permission
from app.modules.rbac.permissions import Permission

router = APIRouter(prefix="/api/v1")

ConsentStatus = Literal["unknown", "granted", "denied"]
ConsentBasis = Literal[
    "consentimiento", "contrato", "interes_legitimo", "obligacion_legal"
]


class ApiModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class AccountCreate(ApiModel):
    name: str = Field(min_length=1)
    industry: str | None = None
    region: str | None = None
    website: str | None = None
    phone: str | None = None
    notes: str | None = None
    owner_user_id: UUID | None = None


class AccountPatch(ApiModel):
    name: str | None = Field(default=None, min_length=1)
    industry: str | None = None
    region: str | None = None
    website: str | None = None
    phone: str | None = None
    notes: str | None = None
    owner_user_id: UUID | None = None


class ContactCreate(ApiModel):
    full_name: str = Field(min_length=1)
    account_id: UUID | None = None
    job_title: str | None = None
    primary_email: str | None = None
    primary_phone: str | None = None
    emails: list[Any] | None = None
    phones: list[Any] | None = None
    social: dict[str, Any] | None = None
    address: str | None = None
    notes: str | None = None
    owner_user_id: UUID | None = None


class ContactPatch(ApiModel):
    full_name: str | None = Field(default=None, min_length=1)
    account_id: UUID | None = None
    job_title: str | None = None
    primary_email: str | None = None
    primary_phone: str | None = None
    emails: list[Any] | None = None
    phones: list[Any] | None = None
    social: dict[str, Any] | None = None
    address: str | None = None
    notes: str | None = None


class ConsentRequest(ApiModel):
    status: ConsentStatus
    basis: ConsentBasis | None = None


class AssignmentRequest(ApiModel):
    owner_user_id: UUID | None = None


def _contacts(session: AsyncSession) -> ContactsService:
    return ContactsService(session)


# ---- accounts -----------------------------------------------------------


@router.get("/accounts")
async def list_accounts(
    principal: Annotated[
        dict[str, Any], Depends(require_permission(Permission.CONTACTS_READ))
    ],
    session: Annotated[AsyncSession, Depends(get_session)],
    q: str | None = None,
    cursor: str | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> dict[str, Any]:
    return await _contacts(session).list_accounts(
        principal, q=q, cursor=cursor, limit=limit
    )


@router.post("/accounts", status_code=201)
async def create_account(
    payload: AccountCreate,
    request: Request,
    principal: Annotated[
        dict[str, Any], Depends(require_permission(Permission.CONTACTS_WRITE))
    ],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict[str, Any]:
    return await _contacts(session).create_account(
        principal,
        name=payload.name,
        industry=payload.industry,
        region=payload.region,
        website=payload.website,
        phone=payload.phone,
        notes=payload.notes,
        owner_user_id=payload.owner_user_id,
        ip=client_ip(request),
    )


@router.get("/accounts/{account_id}")
async def get_account(
    account_id: UUID,
    principal: Annotated[
        dict[str, Any], Depends(require_permission(Permission.CONTACTS_READ))
    ],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict[str, Any]:
    return await _contacts(session).get_account(principal, account_id)


@router.patch("/accounts/{account_id}")
async def update_account(
    account_id: UUID,
    payload: AccountPatch,
    request: Request,
    principal: Annotated[
        dict[str, Any], Depends(require_permission(Permission.CONTACTS_WRITE))
    ],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict[str, Any]:
    return await _contacts(session).update_account(
        principal,
        account_id,
        changes=payload.model_dump(exclude_unset=True, by_alias=False),
        ip=client_ip(request),
    )


@router.post("/accounts/{account_id}/archive")
async def archive_account(
    account_id: UUID,
    request: Request,
    principal: Annotated[
        dict[str, Any], Depends(require_permission(Permission.CONTACTS_WRITE))
    ],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict[str, Any]:
    return await _contacts(session).archive_account(
        principal, account_id, ip=client_ip(request)
    )


@router.get("/accounts/{account_id}/contacts")
async def list_account_contacts(
    account_id: UUID,
    principal: Annotated[
        dict[str, Any], Depends(require_permission(Permission.CONTACTS_READ))
    ],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[dict[str, Any]]:
    return await _contacts(session).list_account_contacts(principal, account_id)


# ---- contacts -----------------------------------------------------------


@router.get("/contacts")
async def list_contacts(
    principal: Annotated[
        dict[str, Any], Depends(require_permission(Permission.CONTACTS_READ))
    ],
    session: Annotated[AsyncSession, Depends(get_session)],
    q: str | None = None,
    account_id: Annotated[UUID | None, Query(alias="accountId")] = None,
    cursor: str | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> dict[str, Any]:
    return await _contacts(session).list_contacts(
        principal, q=q, account_id=account_id, cursor=cursor, limit=limit
    )


@router.post("/contacts", status_code=201)
async def create_contact(
    payload: ContactCreate,
    request: Request,
    principal: Annotated[
        dict[str, Any], Depends(require_permission(Permission.CONTACTS_WRITE))
    ],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict[str, Any]:
    return await _contacts(session).create_contact(
        principal,
        full_name=payload.full_name,
        account_id=payload.account_id,
        job_title=payload.job_title,
        primary_email=payload.primary_email,
        primary_phone=payload.primary_phone,
        emails=payload.emails,
        phones=payload.phones,
        social=payload.social,
        address=payload.address,
        notes=payload.notes,
        owner_user_id=payload.owner_user_id,
        ip=client_ip(request),
    )


@router.get("/contacts/{contact_id}")
async def get_contact(
    contact_id: UUID,
    principal: Annotated[
        dict[str, Any], Depends(require_permission(Permission.CONTACTS_READ))
    ],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict[str, Any]:
    return await _contacts(session).get_contact(principal, contact_id)


@router.patch("/contacts/{contact_id}")
async def update_contact(
    contact_id: UUID,
    payload: ContactPatch,
    request: Request,
    principal: Annotated[
        dict[str, Any], Depends(require_permission(Permission.CONTACTS_WRITE))
    ],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict[str, Any]:
    return await _contacts(session).update_contact(
        principal,
        contact_id,
        changes=payload.model_dump(exclude_unset=True, by_alias=False),
        ip=client_ip(request),
    )


@router.post("/contacts/{contact_id}/archive")
async def archive_contact(
    contact_id: UUID,
    request: Request,
    principal: Annotated[
        dict[str, Any], Depends(require_permission(Permission.CONTACTS_WRITE))
    ],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict[str, Any]:
    return await _contacts(session).archive_contact(
        principal, contact_id, ip=client_ip(request)
    )


@router.post("/contacts/{contact_id}/consent")
async def record_consent(
    contact_id: UUID,
    payload: ConsentRequest,
    request: Request,
    principal: Annotated[
        dict[str, Any], Depends(require_permission(Permission.CONTACTS_WRITE))
    ],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict[str, Any]:
    return await _contacts(session).record_consent(
        principal,
        contact_id,
        status=payload.status,
        basis=payload.basis,
        ip=client_ip(request),
    )


@router.post("/contacts/{contact_id}/assignment")
async def assign_contact(
    contact_id: UUID,
    payload: AssignmentRequest,
    request: Request,
    principal: Annotated[
        dict[str, Any], Depends(require_permission(Permission.CONTACTS_WRITE))
    ],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict[str, Any]:
    return await _contacts(session).assign_contact(
        principal,
        contact_id,
        owner_user_id=payload.owner_user_id,
        ip=client_ip(request),
    )
