from decimal import Decimal
from datetime import date
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.http import client_ip
from app.db.engine import get_session
from app.modules.pipeline.service import PipelineService
from app.modules.rbac.deps import require_permission
from app.modules.rbac.permissions import Permission

router = APIRouter(prefix="/api/v1")

DealStatus = Literal["open", "won", "lost"]


class ApiModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class PipelineCreate(ApiModel):
    name: str = Field(min_length=1)
    is_default: bool = False


class PipelinePatch(ApiModel):
    name: str | None = Field(default=None, min_length=1)
    is_default: bool | None = None


class StageCreate(ApiModel):
    name: str = Field(min_length=1)
    probability: int = Field(default=0, ge=0, le=100)
    rotting_days: int | None = Field(default=None, gt=0)


class StagePatch(ApiModel):
    name: str | None = Field(default=None, min_length=1)
    probability: int | None = Field(default=None, ge=0, le=100)
    rotting_days: int | None = Field(default=None, gt=0)


class StageReorder(ApiModel):
    stage_ids: list[UUID]


class DealCreate(ApiModel):
    name: str = Field(min_length=1)
    pipeline_id: UUID
    stage_id: UUID | None = None
    value: Decimal | None = Field(default=None, ge=0)
    currency: str | None = None
    contact_id: UUID | None = None
    account_id: UUID | None = None
    owner_user_id: UUID | None = None
    close_date: date | None = None
    probability: int | None = Field(default=None, ge=0, le=100)


class DealPatch(ApiModel):
    name: str | None = Field(default=None, min_length=1)
    value: Decimal | None = Field(default=None, ge=0)
    currency: str | None = None
    contact_id: UUID | None = None
    account_id: UUID | None = None
    owner_user_id: UUID | None = None
    close_date: date | None = None
    probability: int | None = Field(default=None, ge=0, le=100)


class DealStageMove(ApiModel):
    to_stage_id: UUID
    reason: str | None = None


class DealStatusRequest(ApiModel):
    status: DealStatus
    lost_reason: str | None = None


def _pipeline(session: AsyncSession) -> PipelineService:
    return PipelineService(session)


# ---- pipelines & stages -------------------------------------------------


@router.get("/pipelines")
async def list_pipelines(
    principal: Annotated[
        dict[str, Any], Depends(require_permission(Permission.PIPELINE_READ))
    ],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict[str, Any]:
    return await _pipeline(session).list_pipelines(principal)


@router.post("/pipelines", status_code=201)
async def create_pipeline(
    payload: PipelineCreate,
    request: Request,
    principal: Annotated[
        dict[str, Any], Depends(require_permission(Permission.PIPELINE_MANAGE))
    ],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict[str, Any]:
    return await _pipeline(session).create_pipeline(
        principal,
        name=payload.name,
        is_default=payload.is_default,
        ip=client_ip(request),
    )


@router.patch("/pipelines/{pipeline_id}")
async def update_pipeline(
    pipeline_id: UUID,
    payload: PipelinePatch,
    request: Request,
    principal: Annotated[
        dict[str, Any], Depends(require_permission(Permission.PIPELINE_MANAGE))
    ],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict[str, Any]:
    return await _pipeline(session).update_pipeline(
        principal,
        pipeline_id,
        changes=payload.model_dump(exclude_unset=True, by_alias=False),
        ip=client_ip(request),
    )


@router.post("/pipelines/{pipeline_id}/archive")
async def archive_pipeline(
    pipeline_id: UUID,
    request: Request,
    principal: Annotated[
        dict[str, Any], Depends(require_permission(Permission.PIPELINE_MANAGE))
    ],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict[str, Any]:
    return await _pipeline(session).archive_pipeline(
        principal, pipeline_id, ip=client_ip(request)
    )


@router.post("/pipelines/{pipeline_id}/stages", status_code=201)
async def add_stage(
    pipeline_id: UUID,
    payload: StageCreate,
    request: Request,
    principal: Annotated[
        dict[str, Any], Depends(require_permission(Permission.PIPELINE_MANAGE))
    ],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict[str, Any]:
    return await _pipeline(session).add_stage(
        principal,
        pipeline_id,
        name=payload.name,
        probability=payload.probability,
        rotting_days=payload.rotting_days,
        ip=client_ip(request),
    )


@router.patch("/stages/{stage_id}")
async def update_stage(
    stage_id: UUID,
    payload: StagePatch,
    request: Request,
    principal: Annotated[
        dict[str, Any], Depends(require_permission(Permission.PIPELINE_MANAGE))
    ],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict[str, Any]:
    return await _pipeline(session).update_stage(
        principal,
        stage_id,
        changes=payload.model_dump(exclude_unset=True, by_alias=False),
        ip=client_ip(request),
    )


@router.post("/pipelines/{pipeline_id}/stages/reorder")
async def reorder_stages(
    pipeline_id: UUID,
    payload: StageReorder,
    request: Request,
    principal: Annotated[
        dict[str, Any], Depends(require_permission(Permission.PIPELINE_MANAGE))
    ],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict[str, Any]:
    return await _pipeline(session).reorder_stages(
        principal,
        pipeline_id,
        stage_ids=payload.stage_ids,
        ip=client_ip(request),
    )


@router.delete("/stages/{stage_id}", status_code=204)
async def delete_stage(
    stage_id: UUID,
    request: Request,
    principal: Annotated[
        dict[str, Any], Depends(require_permission(Permission.PIPELINE_MANAGE))
    ],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> Response:
    await _pipeline(session).delete_stage(
        principal, stage_id, ip=client_ip(request)
    )
    return Response(status_code=204)


@router.get("/pipelines/{pipeline_id}/board")
async def pipeline_board(
    pipeline_id: UUID,
    principal: Annotated[
        dict[str, Any], Depends(require_permission(Permission.PIPELINE_READ))
    ],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict[str, Any]:
    return await _pipeline(session).board(principal, pipeline_id)


@router.get("/pipelines/{pipeline_id}/forecast")
async def pipeline_forecast(
    pipeline_id: UUID,
    principal: Annotated[
        dict[str, Any], Depends(require_permission(Permission.PIPELINE_READ))
    ],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict[str, Any]:
    return await _pipeline(session).forecast(principal, pipeline_id)


# ---- deals --------------------------------------------------------------


@router.get("/deals")
async def list_deals(
    principal: Annotated[
        dict[str, Any], Depends(require_permission(Permission.PIPELINE_READ))
    ],
    session: Annotated[AsyncSession, Depends(get_session)],
    pipeline_id: Annotated[UUID | None, Query(alias="pipelineId")] = None,
    stage_id: Annotated[UUID | None, Query(alias="stageId")] = None,
    status: DealStatus | None = None,
    q: str | None = None,
    cursor: str | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> dict[str, Any]:
    return await _pipeline(session).list_deals(
        principal,
        pipeline_id=pipeline_id,
        stage_id=stage_id,
        status=status,
        q=q,
        cursor=cursor,
        limit=limit,
    )


@router.post("/deals", status_code=201)
async def create_deal(
    payload: DealCreate,
    request: Request,
    principal: Annotated[
        dict[str, Any], Depends(require_permission(Permission.DEAL_WRITE))
    ],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict[str, Any]:
    return await _pipeline(session).create_deal(
        principal,
        name=payload.name,
        pipeline_id=payload.pipeline_id,
        stage_id=payload.stage_id,
        value=payload.value,
        currency=payload.currency,
        contact_id=payload.contact_id,
        account_id=payload.account_id,
        owner_user_id=payload.owner_user_id,
        close_date=payload.close_date,
        probability=payload.probability,
        ip=client_ip(request),
    )


@router.get("/deals/{deal_id}")
async def get_deal(
    deal_id: UUID,
    principal: Annotated[
        dict[str, Any], Depends(require_permission(Permission.PIPELINE_READ))
    ],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict[str, Any]:
    return await _pipeline(session).get_deal(principal, deal_id)


@router.patch("/deals/{deal_id}")
async def update_deal(
    deal_id: UUID,
    payload: DealPatch,
    request: Request,
    principal: Annotated[
        dict[str, Any], Depends(require_permission(Permission.DEAL_WRITE))
    ],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict[str, Any]:
    return await _pipeline(session).update_deal(
        principal,
        deal_id,
        changes=payload.model_dump(exclude_unset=True, by_alias=False),
        ip=client_ip(request),
    )


@router.post("/deals/{deal_id}/stage")
async def move_deal_stage(
    deal_id: UUID,
    payload: DealStageMove,
    request: Request,
    principal: Annotated[
        dict[str, Any], Depends(require_permission(Permission.DEAL_WRITE))
    ],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict[str, Any]:
    return await _pipeline(session).move_stage(
        principal,
        deal_id,
        to_stage_id=payload.to_stage_id,
        reason=payload.reason,
        ip=client_ip(request),
    )


@router.post("/deals/{deal_id}/status")
async def set_deal_status(
    deal_id: UUID,
    payload: DealStatusRequest,
    request: Request,
    principal: Annotated[
        dict[str, Any], Depends(require_permission(Permission.DEAL_WRITE))
    ],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict[str, Any]:
    return await _pipeline(session).set_status(
        principal,
        deal_id,
        status=payload.status,
        lost_reason=payload.lost_reason,
        ip=client_ip(request),
    )


@router.post("/deals/{deal_id}/archive")
async def archive_deal(
    deal_id: UUID,
    request: Request,
    principal: Annotated[
        dict[str, Any], Depends(require_permission(Permission.DEAL_WRITE))
    ],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict[str, Any]:
    return await _pipeline(session).archive_deal(
        principal, deal_id, ip=client_ip(request)
    )


@router.get("/deals/{deal_id}/history")
async def deal_history(
    deal_id: UUID,
    principal: Annotated[
        dict[str, Any], Depends(require_permission(Permission.PIPELINE_READ))
    ],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict[str, Any]:
    return await _pipeline(session).deal_history(principal, deal_id)
