from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.db.identifiers import SCHEMA_NAME_RE
from app.db.search_path import set_search_path
from app.modules.audit.service import AuditService
from app.modules.tenancy.models import Tenant

_MAX_LIMIT = 100
_DEFAULT_LIMIT = 50

PIPELINE_COLS = "id, name, is_default, archived_at, created_at, updated_at"
STAGE_COLS = (
    "id, pipeline_id, name, position, probability, rotting_days, "
    "created_at, updated_at"
)
DEAL_SELECT = """
    SELECT
        d.id, d.pipeline_id, d.stage_id, d.name, d.value, d.currency,
        d.contact_id, d.account_id, d.owner_user_id, d.close_date,
        d.probability, d.status, d.lost_reason, d.stage_changed_at,
        d.created_at, d.updated_at,
        EXTRACT(DAY FROM now() - d.stage_changed_at)::int AS days_in_stage,
        s.rotting_days AS stage_rotting_days
    FROM deals d
    JOIN stages s ON s.id = d.stage_id
"""

_DEAL_TEXT_FIELDS = ("name", "currency", "lost_reason")

_TWO_PLACES = Decimal("0.01")


def _not_found() -> AppError:
    return AppError(404, "not_found", "No encontrado", "No encontrado.")


def _validation_error(detail: str = "Revisa los campos enviados.") -> AppError:
    return AppError(422, "validation_error", "Datos inválidos", detail)


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.isoformat() + "Z"
    return value.isoformat().replace("+00:00", "Z")


def _date(value: date | None) -> str | None:
    return value.isoformat() if value is not None else None


def _money(value: Any) -> str:
    amount = value if isinstance(value, Decimal) else Decimal(str(value or 0))
    return str(amount.quantize(_TWO_PLACES))


def _uuid(value: Any) -> str | None:
    return str(value) if value is not None else None


def _clamp_limit(limit: int | None) -> int:
    if limit is None:
        return _DEFAULT_LIMIT
    if limit < 1:
        return 1
    if limit > _MAX_LIMIT:
        return _MAX_LIMIT
    return limit


def _cursor_uuid(cursor: str | None) -> UUID | None:
    if not cursor:
        return None
    try:
        return UUID(cursor)
    except ValueError as exc:
        raise _validation_error() from exc


def _serialize_pipeline(row: Any, stages: list[dict[str, Any]]) -> dict[str, Any]:
    mapping = dict(row)
    return {
        "id": str(mapping["id"]),
        "name": mapping["name"],
        "isDefault": bool(mapping["is_default"]),
        "archivedAt": _iso(mapping.get("archived_at")),
        "createdAt": _iso(mapping["created_at"]),
        "updatedAt": _iso(mapping["updated_at"]),
        "stages": stages,
    }


def _serialize_stage(row: Any) -> dict[str, Any]:
    mapping = dict(row)
    return {
        "id": str(mapping["id"]),
        "pipelineId": str(mapping["pipeline_id"]),
        "name": mapping["name"],
        "position": int(mapping["position"]),
        "probability": int(mapping["probability"]),
        "rottingDays": (
            int(mapping["rotting_days"])
            if mapping.get("rotting_days") is not None
            else None
        ),
        "createdAt": _iso(mapping["created_at"]),
        "updatedAt": _iso(mapping["updated_at"]),
    }


def _serialize_deal(row: Any) -> dict[str, Any]:
    mapping = dict(row)
    status = mapping["status"]
    days_in_stage = int(mapping["days_in_stage"])
    rotting_days = mapping.get("stage_rotting_days")
    is_rotting = (
        status == "open"
        and rotting_days is not None
        and days_in_stage > int(rotting_days)
    )
    probability = mapping.get("probability")
    return {
        "id": str(mapping["id"]),
        "pipelineId": str(mapping["pipeline_id"]),
        "stageId": str(mapping["stage_id"]),
        "name": mapping["name"],
        "value": _money(mapping["value"]),
        "currency": mapping["currency"],
        "contactId": _uuid(mapping.get("contact_id")),
        "accountId": _uuid(mapping.get("account_id")),
        "ownerUserId": _uuid(mapping.get("owner_user_id")),
        "closeDate": _date(mapping.get("close_date")),
        "probability": int(probability) if probability is not None else None,
        "status": status,
        "lostReason": mapping.get("lost_reason"),
        "stageChangedAt": _iso(mapping["stage_changed_at"]),
        "daysInStage": days_in_stage,
        "isRotting": bool(is_rotting),
        "createdAt": _iso(mapping["created_at"]),
        "updatedAt": _iso(mapping["updated_at"]),
    }


class PipelineService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._audit = AuditService()

    # ---- pipelines ------------------------------------------------------

    async def list_pipelines(self, actor: dict[str, Any]) -> dict[str, Any]:
        tenant = await self._tenant_for(actor)
        await self._bind(tenant.schema_name)
        result = await self._session.execute(
            text(
                f"""
                SELECT {PIPELINE_COLS}
                FROM pipelines
                WHERE archived_at IS NULL
                ORDER BY is_default DESC, created_at ASC, id ASC
                """
            )
        )
        pipelines = list(result.mappings())
        items = []
        for row in pipelines:
            stages = await self._stages_for(row["id"])
            items.append(_serialize_pipeline(row, stages))
        return {"items": items}

    async def create_pipeline(
        self, actor: dict[str, Any], *, name: str, is_default: bool, ip: str
    ) -> dict[str, Any]:
        tenant = await self._tenant_for(actor)
        await self._bind(tenant.schema_name)
        pipeline_id = uuid4()
        if is_default:
            await self._clear_default(None)
        result = await self._session.execute(
            text(
                f"""
                INSERT INTO pipelines (id, name, is_default)
                VALUES (:id, :name, :is_default)
                RETURNING {PIPELINE_COLS}
                """
            ),
            {"id": pipeline_id, "name": name, "is_default": is_default},
        )
        row = result.mappings().one()
        await self._audit_event(
            tenant, actor, ip, "pipeline.created", {"pipelineId": str(pipeline_id)}
        )
        await self._session.commit()
        return _serialize_pipeline(row, [])

    async def update_pipeline(
        self, actor: dict[str, Any], pipeline_id: UUID, *, changes: dict[str, Any], ip: str
    ) -> dict[str, Any]:
        tenant = await self._tenant_for(actor)
        await self._require_active_pipeline(tenant.schema_name, pipeline_id)
        await self._bind(tenant.schema_name)
        assignments: list[str] = []
        params: dict[str, Any] = {"id": pipeline_id}
        if "name" in changes:
            assignments.append("name = :name")
            params["name"] = changes["name"]
        if changes.get("is_default") is True:
            await self._clear_default(pipeline_id)
            assignments.append("is_default = true")
        elif changes.get("is_default") is False:
            assignments.append("is_default = false")
        if assignments:
            result = await self._session.execute(
                text(
                    f"""
                    UPDATE pipelines
                    SET {", ".join(assignments)}, updated_at = now()
                    WHERE id = :id AND archived_at IS NULL
                    RETURNING {PIPELINE_COLS}
                    """
                ),
                params,
            )
            row = result.mappings().first()
            if row is None:
                raise _not_found()
        else:
            row = await self._pipeline_row(pipeline_id)
        await self._audit_event(
            tenant, actor, ip, "pipeline.updated", {"pipelineId": str(pipeline_id)}
        )
        await self._session.commit()
        stages = await self._stages_for(pipeline_id)
        return _serialize_pipeline(row, stages)

    async def archive_pipeline(
        self, actor: dict[str, Any], pipeline_id: UUID, *, ip: str
    ) -> dict[str, Any]:
        tenant = await self._tenant_for(actor)
        pipeline = await self._require_active_pipeline(tenant.schema_name, pipeline_id)
        if bool(pipeline["is_default"]):
            raise _validation_error("No puedes archivar el pipeline predeterminado.")
        await self._bind(tenant.schema_name)
        open_deals = (
            await self._session.execute(
                text(
                    """
                    SELECT 1 FROM deals
                    WHERE pipeline_id = :id
                      AND status = 'open'
                      AND archived_at IS NULL
                    LIMIT 1
                    """
                ),
                {"id": pipeline_id},
            )
        ).first()
        if open_deals is not None:
            raise _validation_error(
                "No puedes archivar un pipeline con negocios abiertos."
            )
        result = await self._session.execute(
            text(
                f"""
                UPDATE pipelines
                SET archived_at = now(), is_default = false, updated_at = now()
                WHERE id = :id AND archived_at IS NULL
                RETURNING {PIPELINE_COLS}
                """
            ),
            {"id": pipeline_id},
        )
        row = result.mappings().first()
        if row is None:
            raise _not_found()
        await self._audit_event(
            tenant, actor, ip, "pipeline.archived", {"pipelineId": str(pipeline_id)}
        )
        await self._session.commit()
        return _serialize_pipeline(row, [])

    # ---- stages ---------------------------------------------------------

    async def add_stage(
        self,
        actor: dict[str, Any],
        pipeline_id: UUID,
        *,
        name: str,
        probability: int,
        rotting_days: int | None,
        ip: str,
    ) -> dict[str, Any]:
        tenant = await self._tenant_for(actor)
        await self._require_active_pipeline(tenant.schema_name, pipeline_id)
        await self._bind(tenant.schema_name)
        stage_id = uuid4()
        result = await self._session.execute(
            text(
                f"""
                INSERT INTO stages (id, pipeline_id, name, position, probability, rotting_days)
                VALUES (
                    :id, :pipeline_id, :name,
                    (SELECT COALESCE(MAX(position), 0) + 1 FROM stages WHERE pipeline_id = :pipeline_id),
                    :probability, :rotting_days
                )
                RETURNING {STAGE_COLS}
                """
            ),
            {
                "id": stage_id,
                "pipeline_id": pipeline_id,
                "name": name,
                "probability": probability,
                "rotting_days": rotting_days,
            },
        )
        row = result.mappings().one()
        await self._audit_event(
            tenant,
            actor,
            ip,
            "stage.created",
            {"pipelineId": str(pipeline_id), "stageId": str(stage_id)},
        )
        await self._session.commit()
        return _serialize_stage(row)

    async def update_stage(
        self, actor: dict[str, Any], stage_id: UUID, *, changes: dict[str, Any], ip: str
    ) -> dict[str, Any]:
        tenant = await self._tenant_for(actor)
        stage = await self._stage_row(tenant.schema_name, stage_id)
        await self._bind(tenant.schema_name)
        assignments: list[str] = []
        params: dict[str, Any] = {"id": stage_id}
        if "name" in changes:
            assignments.append("name = :name")
            params["name"] = changes["name"]
        if "probability" in changes:
            assignments.append("probability = :probability")
            params["probability"] = changes["probability"]
        if "rotting_days" in changes:
            assignments.append("rotting_days = :rotting_days")
            params["rotting_days"] = changes["rotting_days"]
        if not assignments:
            return _serialize_stage(stage)
        result = await self._session.execute(
            text(
                f"""
                UPDATE stages
                SET {", ".join(assignments)}, updated_at = now()
                WHERE id = :id
                RETURNING {STAGE_COLS}
                """
            ),
            params,
        )
        row = result.mappings().one()
        await self._audit_event(
            tenant,
            actor,
            ip,
            "stage.updated",
            {"pipelineId": str(stage["pipeline_id"]), "stageId": str(stage_id)},
        )
        await self._session.commit()
        return _serialize_stage(row)

    async def reorder_stages(
        self, actor: dict[str, Any], pipeline_id: UUID, *, stage_ids: list[UUID], ip: str
    ) -> dict[str, Any]:
        tenant = await self._tenant_for(actor)
        await self._require_active_pipeline(tenant.schema_name, pipeline_id)
        await self._bind(tenant.schema_name)
        existing = (
            await self._session.execute(
                text("SELECT id FROM stages WHERE pipeline_id = :pipeline_id"),
                {"pipeline_id": pipeline_id},
            )
        ).scalars()
        existing_ids = {str(sid) for sid in existing}
        given_ids = [str(sid) for sid in stage_ids]
        if len(given_ids) != len(existing_ids) or set(given_ids) != existing_ids:
            raise _validation_error(
                "La lista de etapas debe coincidir con las etapas del pipeline."
            )
        for index, sid in enumerate(stage_ids, start=1):
            await self._session.execute(
                text(
                    """
                    UPDATE stages SET position = :position, updated_at = now()
                    WHERE id = :id AND pipeline_id = :pipeline_id
                    """
                ),
                {"position": index, "id": sid, "pipeline_id": pipeline_id},
            )
        await self._audit_event(
            tenant,
            actor,
            ip,
            "stage.reordered",
            {"pipelineId": str(pipeline_id), "stageIds": given_ids},
        )
        await self._session.commit()
        stages = await self._stages_for(pipeline_id)
        row = await self._pipeline_row(pipeline_id)
        return _serialize_pipeline(row, stages)

    async def delete_stage(
        self, actor: dict[str, Any], stage_id: UUID, *, ip: str
    ) -> None:
        tenant = await self._tenant_for(actor)
        stage = await self._stage_row(tenant.schema_name, stage_id)
        pipeline_id = stage["pipeline_id"]
        await self._bind(tenant.schema_name)
        stage_count = (
            await self._session.execute(
                text("SELECT count(*) FROM stages WHERE pipeline_id = :pipeline_id"),
                {"pipeline_id": pipeline_id},
            )
        ).scalar()
        if int(stage_count or 0) <= 1:
            raise _validation_error("No puedes eliminar la última etapa del pipeline.")
        active_deals = (
            await self._session.execute(
                text(
                    """
                    SELECT 1 FROM deals
                    WHERE stage_id = :id AND archived_at IS NULL
                    LIMIT 1
                    """
                ),
                {"id": stage_id},
            )
        ).first()
        if active_deals is not None:
            raise _validation_error("No puedes eliminar una etapa con negocios activos.")
        await self._session.execute(
            text("DELETE FROM stages WHERE id = :id"), {"id": stage_id}
        )
        await self._audit_event(
            tenant,
            actor,
            ip,
            "stage.deleted",
            {"pipelineId": str(pipeline_id), "stageId": str(stage_id)},
        )
        await self._session.commit()

    # ---- board & forecast ----------------------------------------------

    async def board(self, actor: dict[str, Any], pipeline_id: UUID) -> dict[str, Any]:
        tenant = await self._tenant_for(actor)
        pipeline = await self._require_active_pipeline(tenant.schema_name, pipeline_id)
        stages = await self._stages_for(pipeline_id)
        await self._bind(tenant.schema_name)
        result = await self._session.execute(
            text(
                DEAL_SELECT
                + """
                WHERE d.pipeline_id = :pipeline_id
                  AND d.status = 'open'
                  AND d.archived_at IS NULL
                ORDER BY d.stage_changed_at DESC, d.id DESC
                """
            ),
            {"pipeline_id": pipeline_id},
        )
        deals = [_serialize_deal(row) for row in result.mappings()]
        grouped: dict[str, list[dict[str, Any]]] = {stage["id"]: [] for stage in stages}
        for deal in deals:
            grouped.setdefault(deal["stageId"], []).append(deal)
        columns = [
            {"stage": stage, "deals": grouped.get(stage["id"], [])} for stage in stages
        ]
        return {
            "pipeline": _serialize_pipeline(pipeline, stages),
            "stages": columns,
        }

    async def forecast(self, actor: dict[str, Any], pipeline_id: UUID) -> dict[str, Any]:
        tenant = await self._tenant_for(actor)
        await self._require_active_pipeline(tenant.schema_name, pipeline_id)
        stages = await self._stages_for(pipeline_id)
        await self._bind(tenant.schema_name)
        result = await self._session.execute(
            text(
                """
                SELECT
                    d.stage_id, d.value, d.probability, d.close_date
                FROM deals d
                WHERE d.pipeline_id = :pipeline_id
                  AND d.status = 'open'
                  AND d.archived_at IS NULL
                """
            ),
            {"pipeline_id": pipeline_id},
        )
        rows = list(result.mappings())
        stage_stats: dict[str, dict[str, Any]] = {
            stage["id"]: {"count": 0, "sum": Decimal("0"), "weighted": Decimal("0")}
            for stage in stages
        }
        month_stats: dict[str, dict[str, Decimal]] = {}
        total_count = 0
        total_sum = Decimal("0")
        total_weighted = Decimal("0")
        for row in rows:
            stage_id = str(row["stage_id"])
            value = row["value"] if isinstance(row["value"], Decimal) else Decimal(
                str(row["value"] or 0)
            )
            probability = int(row["probability"]) if row["probability"] is not None else 0
            weighted = value * Decimal(probability) / Decimal(100)
            bucket = stage_stats.setdefault(
                stage_id, {"count": 0, "sum": Decimal("0"), "weighted": Decimal("0")}
            )
            bucket["count"] += 1
            bucket["sum"] += value
            bucket["weighted"] += weighted
            total_count += 1
            total_sum += value
            total_weighted += weighted
            close_date = row["close_date"]
            if close_date is not None:
                month_key = close_date.strftime("%Y-%m")
                month_bucket = month_stats.setdefault(
                    month_key, {"sum": Decimal("0"), "weighted": Decimal("0")}
                )
                month_bucket["sum"] += value
                month_bucket["weighted"] += weighted
        stages_out = [
            {
                "stageId": stage["id"],
                "name": stage["name"],
                "count": stage_stats[stage["id"]]["count"],
                "sum": _money(stage_stats[stage["id"]]["sum"]),
                "weighted": _money(stage_stats[stage["id"]]["weighted"]),
            }
            for stage in stages
        ]
        months_out = [
            {
                "month": month,
                "sum": _money(values["sum"]),
                "weighted": _money(values["weighted"]),
            }
            for month, values in sorted(month_stats.items())
        ]
        return {
            "pipelineId": str(pipeline_id),
            "currency": "COP",
            "stages": stages_out,
            "totals": {
                "count": total_count,
                "sum": _money(total_sum),
                "weighted": _money(total_weighted),
            },
            "months": months_out,
        }

    # ---- deals ----------------------------------------------------------

    async def list_deals(
        self,
        actor: dict[str, Any],
        *,
        pipeline_id: UUID | None = None,
        stage_id: UUID | None = None,
        status: str | None = None,
        q: str | None = None,
        cursor: str | None = None,
        limit: int | None = None,
    ) -> dict[str, Any]:
        tenant = await self._tenant_for(actor)
        await self._bind(tenant.schema_name)
        page_size = _clamp_limit(limit)
        result = await self._session.execute(
            text(
                DEAL_SELECT
                + """
                WHERE d.archived_at IS NULL
                  AND (CAST(:pipeline_id AS uuid) IS NULL OR d.pipeline_id = CAST(:pipeline_id AS uuid))
                  AND (CAST(:stage_id AS uuid) IS NULL OR d.stage_id = CAST(:stage_id AS uuid))
                  AND (CAST(:status AS text) IS NULL OR d.status = CAST(:status AS text))
                  AND (CAST(:q AS text) IS NULL OR d.name ILIKE CAST(:q AS text))
                  AND (
                    CAST(:cursor_id AS uuid) IS NULL
                    OR (d.created_at, d.id) < (
                        SELECT c.created_at, c.id FROM deals c
                        WHERE c.id = CAST(:cursor_id AS uuid)
                    )
                  )
                ORDER BY d.created_at DESC, d.id DESC
                LIMIT :limit
                """
            ),
            {
                "pipeline_id": pipeline_id,
                "stage_id": stage_id,
                "status": status,
                "q": f"%{q}%" if q else None,
                "cursor_id": _cursor_uuid(cursor),
                "limit": page_size + 1,
            },
        )
        rows = list(result.mappings())
        next_cursor: str | None = None
        if len(rows) > page_size:
            rows = rows[:page_size]
            next_cursor = str(rows[-1]["id"])
        page: dict[str, Any] = {"items": [_serialize_deal(row) for row in rows]}
        if next_cursor is not None:
            page["nextCursor"] = next_cursor
        return page

    async def create_deal(
        self,
        actor: dict[str, Any],
        *,
        name: str,
        pipeline_id: UUID,
        stage_id: UUID | None,
        value: Decimal | None,
        currency: str | None,
        contact_id: UUID | None,
        account_id: UUID | None,
        owner_user_id: UUID | None,
        close_date: date | None,
        probability: int | None,
        ip: str,
    ) -> dict[str, Any]:
        tenant = await self._tenant_for(actor)
        await self._require_active_pipeline(tenant.schema_name, pipeline_id)
        await self._bind(tenant.schema_name)
        if stage_id is not None:
            stage = await self._stage_in_pipeline(pipeline_id, stage_id)
        else:
            stage = await self._first_stage(pipeline_id)
        if contact_id is not None:
            await self._require_active_contact(contact_id)
        if account_id is not None:
            await self._require_active_account(account_id)
        deal_id = uuid4()
        final_probability = (
            probability if probability is not None else int(stage["probability"])
        )
        await self._session.execute(
            text(
                """
                INSERT INTO deals (
                    id, pipeline_id, stage_id, name, value, currency,
                    contact_id, account_id, owner_user_id, close_date,
                    probability, status, stage_changed_at
                )
                VALUES (
                    :id, :pipeline_id, :stage_id, :name, :value, :currency,
                    :contact_id, :account_id, :owner_user_id, :close_date,
                    :probability, 'open', now()
                )
                """
            ),
            {
                "id": deal_id,
                "pipeline_id": pipeline_id,
                "stage_id": stage["id"],
                "name": name,
                "value": value if value is not None else Decimal("0"),
                "currency": currency or "COP",
                "contact_id": contact_id,
                "account_id": account_id,
                "owner_user_id": owner_user_id,
                "close_date": close_date,
                "probability": final_probability,
            },
        )
        await self._session.execute(
            text(
                """
                INSERT INTO deal_stage_events
                    (id, deal_id, from_stage_id, to_stage_id, reason, actor_email)
                VALUES (:id, :deal_id, NULL, :to_stage_id, :reason, :actor_email)
                """
            ),
            {
                "id": uuid4(),
                "deal_id": deal_id,
                "to_stage_id": stage["id"],
                "reason": "Creación",
                "actor_email": str(actor.get("email")),
            },
        )
        await self._audit_event(
            tenant, actor, ip, "deal.created", {"dealId": str(deal_id)}
        )
        await self._session.commit()
        row = await self._deal_row(tenant.schema_name, deal_id)
        return _serialize_deal(row)

    async def get_deal(self, actor: dict[str, Any], deal_id: UUID) -> dict[str, Any]:
        tenant = await self._tenant_for(actor)
        row = await self._deal_row(tenant.schema_name, deal_id)
        return _serialize_deal(row)

    async def update_deal(
        self, actor: dict[str, Any], deal_id: UUID, *, changes: dict[str, Any], ip: str
    ) -> dict[str, Any]:
        tenant = await self._tenant_for(actor)
        await self._deal_row(tenant.schema_name, deal_id)
        await self._bind(tenant.schema_name)
        if changes.get("contact_id") is not None:
            await self._require_active_contact(changes["contact_id"])
        if changes.get("account_id") is not None:
            await self._require_active_account(changes["account_id"])
        assignments: list[str] = []
        params: dict[str, Any] = {"id": deal_id}
        for key in _DEAL_TEXT_FIELDS:
            if key in changes:
                assignments.append(f"{key} = :{key}")
                params[key] = changes[key]
        for key in ("value", "probability", "close_date", "owner_user_id"):
            if key in changes:
                assignments.append(f"{key} = :{key}")
                params[key] = changes[key]
        if "contact_id" in changes:
            assignments.append("contact_id = CAST(:contact_id AS uuid)")
            params["contact_id"] = changes["contact_id"]
        if "account_id" in changes:
            assignments.append("account_id = CAST(:account_id AS uuid)")
            params["account_id"] = changes["account_id"]
        if assignments:
            result = await self._session.execute(
                text(
                    f"""
                    UPDATE deals
                    SET {", ".join(assignments)}, updated_at = now()
                    WHERE id = :id AND archived_at IS NULL
                    """
                ),
                params,
            )
            if result.rowcount == 0:
                raise _not_found()
        await self._audit_event(
            tenant, actor, ip, "deal.updated", {"dealId": str(deal_id)}
        )
        await self._session.commit()
        row = await self._deal_row(tenant.schema_name, deal_id)
        return _serialize_deal(row)

    async def move_stage(
        self,
        actor: dict[str, Any],
        deal_id: UUID,
        *,
        to_stage_id: UUID,
        reason: str | None,
        ip: str,
    ) -> dict[str, Any]:
        tenant = await self._tenant_for(actor)
        deal = await self._deal_row(tenant.schema_name, deal_id)
        stage = await self._stage_in_pipeline(deal["pipeline_id"], to_stage_id)
        await self._bind(tenant.schema_name)
        await self._session.execute(
            text(
                """
                INSERT INTO deal_stage_events
                    (id, deal_id, from_stage_id, to_stage_id, reason, actor_email)
                VALUES (:id, :deal_id, :from_stage_id, :to_stage_id, :reason, :actor_email)
                """
            ),
            {
                "id": uuid4(),
                "deal_id": deal_id,
                "from_stage_id": deal["stage_id"],
                "to_stage_id": to_stage_id,
                "reason": reason,
                "actor_email": str(actor.get("email")),
            },
        )
        await self._session.execute(
            text(
                """
                UPDATE deals
                SET stage_id = :stage_id,
                    stage_changed_at = now(),
                    probability = :probability,
                    updated_at = now()
                WHERE id = :id AND archived_at IS NULL
                """
            ),
            {
                "id": deal_id,
                "stage_id": to_stage_id,
                "probability": int(stage["probability"]),
            },
        )
        await self._audit_event(
            tenant,
            actor,
            ip,
            "deal.stage_changed",
            {
                "dealId": str(deal_id),
                "fromStageId": str(deal["stage_id"]),
                "toStageId": str(to_stage_id),
            },
        )
        await self._session.commit()
        row = await self._deal_row(tenant.schema_name, deal_id)
        return _serialize_deal(row)

    async def set_status(
        self,
        actor: dict[str, Any],
        deal_id: UUID,
        *,
        status: str,
        lost_reason: str | None,
        ip: str,
    ) -> dict[str, Any]:
        tenant = await self._tenant_for(actor)
        await self._deal_row(tenant.schema_name, deal_id)
        await self._bind(tenant.schema_name)
        final_lost_reason = lost_reason if status == "lost" else None
        result = await self._session.execute(
            text(
                """
                UPDATE deals
                SET status = :status,
                    lost_reason = :lost_reason,
                    updated_at = now()
                WHERE id = :id AND archived_at IS NULL
                """
            ),
            {"id": deal_id, "status": status, "lost_reason": final_lost_reason},
        )
        if result.rowcount == 0:
            raise _not_found()
        await self._audit_event(
            tenant,
            actor,
            ip,
            "deal.status_changed",
            {"dealId": str(deal_id), "status": status},
        )
        await self._session.commit()
        row = await self._deal_row(tenant.schema_name, deal_id)
        return _serialize_deal(row)

    async def archive_deal(
        self, actor: dict[str, Any], deal_id: UUID, *, ip: str
    ) -> dict[str, Any]:
        tenant = await self._tenant_for(actor)
        row = await self._deal_row(tenant.schema_name, deal_id)
        await self._bind(tenant.schema_name)
        await self._session.execute(
            text(
                """
                UPDATE deals
                SET archived_at = now(), updated_at = now()
                WHERE id = :id AND archived_at IS NULL
                """
            ),
            {"id": deal_id},
        )
        await self._audit_event(
            tenant, actor, ip, "deal.archived", {"dealId": str(deal_id)}
        )
        await self._session.commit()
        result = dict(row)
        result["archived_at"] = datetime.now()
        return _serialize_deal(result)

    async def deal_history(
        self, actor: dict[str, Any], deal_id: UUID
    ) -> dict[str, Any]:
        tenant = await self._tenant_for(actor)
        await self._deal_row(tenant.schema_name, deal_id)
        await self._bind(tenant.schema_name)
        result = await self._session.execute(
            text(
                """
                SELECT
                    e.id, e.from_stage_id, e.to_stage_id, e.reason,
                    e.actor_email, e.occurred_at,
                    fs.name AS from_stage_name, ts.name AS to_stage_name
                FROM deal_stage_events e
                LEFT JOIN stages fs ON fs.id = e.from_stage_id
                LEFT JOIN stages ts ON ts.id = e.to_stage_id
                WHERE e.deal_id = :deal_id
                ORDER BY e.occurred_at DESC, e.id DESC
                """
            ),
            {"deal_id": deal_id},
        )
        items = [
            {
                "id": str(row["id"]),
                "fromStageId": _uuid(row["from_stage_id"]),
                "fromStageName": row["from_stage_name"],
                "toStageId": _uuid(row["to_stage_id"]),
                "toStageName": row["to_stage_name"],
                "reason": row["reason"],
                "actorEmail": row["actor_email"],
                "occurredAt": _iso(row["occurred_at"]),
            }
            for row in result.mappings()
        ]
        return {"items": items}

    # ---- helpers --------------------------------------------------------

    async def _clear_default(self, keep_id: UUID | None) -> None:
        await self._session.execute(
            text(
                """
                UPDATE pipelines
                SET is_default = false, updated_at = now()
                WHERE is_default AND archived_at IS NULL
                  AND (CAST(:keep_id AS uuid) IS NULL OR id <> CAST(:keep_id AS uuid))
                """
            ),
            {"keep_id": keep_id},
        )

    async def _stages_for(self, pipeline_id: Any) -> list[dict[str, Any]]:
        result = await self._session.execute(
            text(
                f"""
                SELECT {STAGE_COLS}
                FROM stages
                WHERE pipeline_id = :pipeline_id
                ORDER BY position ASC, created_at ASC
                """
            ),
            {"pipeline_id": pipeline_id},
        )
        return [_serialize_stage(row) for row in result.mappings()]

    async def _pipeline_row(self, pipeline_id: UUID) -> dict[str, Any]:
        row = (
            await self._session.execute(
                text(
                    f"SELECT {PIPELINE_COLS} FROM pipelines WHERE id = :id"
                ),
                {"id": pipeline_id},
            )
        ).mappings().first()
        if row is None:
            raise _not_found()
        return dict(row)

    async def _require_active_pipeline(
        self, schema_name: str, pipeline_id: UUID
    ) -> dict[str, Any]:
        await self._bind(schema_name)
        row = (
            await self._session.execute(
                text(
                    f"""
                    SELECT {PIPELINE_COLS} FROM pipelines
                    WHERE id = :id AND archived_at IS NULL
                    """
                ),
                {"id": pipeline_id},
            )
        ).mappings().first()
        if row is None:
            raise _validation_error("El pipeline indicado no existe o está archivado.")
        return dict(row)

    async def _stage_row(self, schema_name: str, stage_id: UUID) -> dict[str, Any]:
        await self._bind(schema_name)
        row = (
            await self._session.execute(
                text(f"SELECT {STAGE_COLS} FROM stages WHERE id = :id"),
                {"id": stage_id},
            )
        ).mappings().first()
        if row is None:
            raise _not_found()
        return dict(row)

    async def _stage_in_pipeline(
        self, pipeline_id: Any, stage_id: UUID
    ) -> dict[str, Any]:
        row = (
            await self._session.execute(
                text(
                    f"""
                    SELECT {STAGE_COLS} FROM stages
                    WHERE id = :id AND pipeline_id = :pipeline_id
                    """
                ),
                {"id": stage_id, "pipeline_id": pipeline_id},
            )
        ).mappings().first()
        if row is None:
            raise _validation_error("La etapa no pertenece a este pipeline.")
        return dict(row)

    async def _first_stage(self, pipeline_id: UUID) -> dict[str, Any]:
        row = (
            await self._session.execute(
                text(
                    f"""
                    SELECT {STAGE_COLS} FROM stages
                    WHERE pipeline_id = :pipeline_id
                    ORDER BY position ASC LIMIT 1
                    """
                ),
                {"pipeline_id": pipeline_id},
            )
        ).mappings().first()
        if row is None:
            raise _validation_error("El pipeline no tiene etapas configuradas.")
        return dict(row)

    async def _deal_row(self, schema_name: str, deal_id: UUID) -> dict[str, Any]:
        await self._bind(schema_name)
        row = (
            await self._session.execute(
                text(DEAL_SELECT + " WHERE d.id = :id AND d.archived_at IS NULL"),
                {"id": deal_id},
            )
        ).mappings().first()
        if row is None:
            raise _not_found()
        return dict(row)

    async def _require_active_contact(self, contact_id: UUID) -> None:
        row = (
            await self._session.execute(
                text(
                    "SELECT id FROM contacts WHERE id = :id AND archived_at IS NULL"
                ),
                {"id": contact_id},
            )
        ).first()
        if row is None:
            raise _validation_error("El contacto indicado no existe o está archivado.")

    async def _require_active_account(self, account_id: UUID) -> None:
        row = (
            await self._session.execute(
                text(
                    "SELECT id FROM accounts WHERE id = :id AND archived_at IS NULL"
                ),
                {"id": account_id},
            )
        ).first()
        if row is None:
            raise _validation_error("La cuenta indicada no existe o está archivada.")

    async def _audit_event(
        self,
        tenant: Tenant,
        actor: dict[str, Any],
        ip: str,
        event_type: str,
        payload: dict[str, Any],
    ) -> None:
        await self._audit.append(
            self._session,
            event_type=event_type,
            actor_email=str(actor.get("email")),
            ip_address=ip,
            tenant_id=tenant.id,
            schema_name=tenant.schema_name,
            payload=payload,
        )

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
