from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.db.engine import get_session
from app.modules.audit.service import AuditService
from app.modules.rbac.deps import require_permission
from app.modules.rbac.permissions import Permission

router = APIRouter(prefix="/api/v1")


@router.get("/audit-events")
async def list_audit_events(
    principal: Annotated[
        dict[str, Any], Depends(require_permission(Permission.AUDIT_READ))
    ],
    session: Annotated[AsyncSession, Depends(get_session)],
    cursor: str | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> dict[str, Any]:
    cursor_id: UUID | None = None
    if cursor:
        try:
            cursor_id = UUID(cursor)
        except ValueError as exc:
            raise AppError(
                422,
                "validation_error",
                "Datos inválidos",
                "Revisa los campos enviados.",
            ) from exc
    return await AuditService().list(
        session,
        tenant_id=UUID(str(principal["tenantId"])),
        cursor_id=cursor_id,
        limit=limit,
    )
