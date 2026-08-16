import json
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.db.identifiers import SCHEMA_NAME_RE
from app.db.search_path import set_search_path
from app.modules.audit.service import AuditService
from app.modules.tenancy.models import Tenant

ACCOUNT_COLS = """
    id, name, industry, region, website, phone, notes,
    owner_user_id, created_at, updated_at
"""

CONTACT_COLS = """
    id, account_id, full_name, job_title, primary_email, primary_phone,
    emails, phones, social, address, notes, owner_user_id,
    consent_status, consent_basis, consent_recorded_at, created_at, updated_at
"""

_MAX_LIMIT = 100
_DEFAULT_LIMIT = 50

_ACCOUNT_FIELDS = ("name", "industry", "region", "website", "phone", "notes")
_CONTACT_TEXT_FIELDS = (
    "full_name",
    "job_title",
    "primary_email",
    "primary_phone",
    "address",
    "notes",
)
_CONTACT_JSON_FIELDS = ("emails", "phones", "social")


def _not_found() -> AppError:
    return AppError(
        404,
        "not_found",
        "No encontrado",
        "No encontrado.",
    )


def _validation_error(detail: str = "Revisa los campos enviados.") -> AppError:
    return AppError(422, "validation_error", "Datos inválidos", detail)


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.isoformat() + "Z"
    return value.isoformat().replace("+00:00", "Z")


def _json_value(value: Any) -> Any:
    if isinstance(value, str):
        return json.loads(value)
    return value


def _serialize_account(row: Any) -> dict[str, Any]:
    mapping = dict(row)
    return {
        "id": str(mapping["id"]),
        "name": mapping["name"],
        "industry": mapping.get("industry"),
        "region": mapping.get("region"),
        "website": mapping.get("website"),
        "phone": mapping.get("phone"),
        "notes": mapping.get("notes"),
        "ownerUserId": (
            str(mapping["owner_user_id"])
            if mapping.get("owner_user_id") is not None
            else None
        ),
        "createdAt": _iso(mapping["created_at"]),
        "updatedAt": _iso(mapping["updated_at"]),
    }


def _serialize_contact(row: Any) -> dict[str, Any]:
    mapping = dict(row)
    return {
        "id": str(mapping["id"]),
        "accountId": (
            str(mapping["account_id"])
            if mapping.get("account_id") is not None
            else None
        ),
        "fullName": mapping["full_name"],
        "jobTitle": mapping.get("job_title"),
        "primaryEmail": mapping.get("primary_email"),
        "primaryPhone": mapping.get("primary_phone"),
        "emails": _json_value(mapping.get("emails")),
        "phones": _json_value(mapping.get("phones")),
        "social": _json_value(mapping.get("social")),
        "address": mapping.get("address"),
        "notes": mapping.get("notes"),
        "ownerUserId": (
            str(mapping["owner_user_id"])
            if mapping.get("owner_user_id") is not None
            else None
        ),
        "consentStatus": mapping["consent_status"],
        "consentBasis": mapping.get("consent_basis"),
        "consentRecordedAt": _iso(mapping.get("consent_recorded_at")),
        "createdAt": _iso(mapping["created_at"]),
        "updatedAt": _iso(mapping["updated_at"]),
    }


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


class ContactsService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._audit = AuditService()

    # ---- accounts -------------------------------------------------------

    async def list_accounts(
        self,
        actor: dict[str, Any],
        *,
        q: str | None = None,
        cursor: str | None = None,
        limit: int | None = None,
    ) -> dict[str, Any]:
        tenant = await self._tenant_for(actor)
        await self._bind(tenant.schema_name)
        page_size = _clamp_limit(limit)
        result = await self._session.execute(
            text(
                f"""
                SELECT {ACCOUNT_COLS}
                FROM accounts
                WHERE archived_at IS NULL
                  AND (
                    CAST(:q AS text) IS NULL
                    OR lower(name) LIKE CAST(:q AS text)
                  )
                  AND (
                    CAST(:cursor_id AS uuid) IS NULL
                    OR (created_at, id) < (
                        SELECT a.created_at, a.id
                        FROM accounts a
                        WHERE a.id = CAST(:cursor_id AS uuid)
                    )
                  )
                ORDER BY created_at DESC, id DESC
                LIMIT :limit
                """
            ),
            {
                "q": f"%{q.lower()}%" if q else None,
                "cursor_id": _cursor_uuid(cursor),
                "limit": page_size + 1,
            },
        )
        return self._page(result, _serialize_account, page_size)

    async def create_account(
        self,
        actor: dict[str, Any],
        *,
        name: str,
        industry: str | None,
        region: str | None,
        website: str | None,
        phone: str | None,
        notes: str | None,
        owner_user_id: UUID | None,
        ip: str,
    ) -> dict[str, Any]:
        tenant = await self._tenant_for(actor)
        await self._bind(tenant.schema_name)
        account_id = uuid4()
        result = await self._session.execute(
            text(
                f"""
                INSERT INTO accounts (
                    id, name, industry, region, website, phone, notes,
                    owner_user_id
                )
                VALUES (
                    :id, :name, :industry, :region, :website, :phone, :notes,
                    :owner_user_id
                )
                RETURNING {ACCOUNT_COLS}
                """
            ),
            {
                "id": account_id,
                "name": name,
                "industry": industry,
                "region": region,
                "website": website,
                "phone": phone,
                "notes": notes,
                "owner_user_id": owner_user_id,
            },
        )
        row = result.mappings().one()
        await self._audit.append(
            self._session,
            event_type="account.created",
            actor_email=str(actor.get("email")),
            ip_address=ip,
            tenant_id=tenant.id,
            schema_name=tenant.schema_name,
            payload={"accountId": str(account_id)},
        )
        await self._session.commit()
        return _serialize_account(row)

    async def get_account(
        self, actor: dict[str, Any], account_id: UUID
    ) -> dict[str, Any]:
        tenant = await self._tenant_for(actor)
        row = await self._account_row(tenant.schema_name, account_id)
        return _serialize_account(row)

    async def update_account(
        self,
        actor: dict[str, Any],
        account_id: UUID,
        *,
        changes: dict[str, Any],
        ip: str,
    ) -> dict[str, Any]:
        tenant = await self._tenant_for(actor)
        await self._account_row(tenant.schema_name, account_id)
        fields = {k: v for k, v in changes.items() if k in _ACCOUNT_FIELDS}
        if "owner_user_id" in changes:
            fields["owner_user_id"] = changes["owner_user_id"]
        if not fields:
            row = await self._account_row(tenant.schema_name, account_id)
            return _serialize_account(row)
        assignments = ", ".join(f"{key} = :{key}" for key in fields)
        params: dict[str, Any] = dict(fields)
        params["id"] = account_id
        await self._bind(tenant.schema_name)
        result = await self._session.execute(
            text(
                f"""
                UPDATE accounts
                SET {assignments}, updated_at = now()
                WHERE id = :id AND archived_at IS NULL
                RETURNING {ACCOUNT_COLS}
                """
            ),
            params,
        )
        row = result.mappings().first()
        if row is None:
            raise _not_found()
        await self._audit.append(
            self._session,
            event_type="account.updated",
            actor_email=str(actor.get("email")),
            ip_address=ip,
            tenant_id=tenant.id,
            schema_name=tenant.schema_name,
            payload={"accountId": str(account_id), "changed": sorted(fields.keys())},
        )
        await self._session.commit()
        return _serialize_account(row)

    async def archive_account(
        self, actor: dict[str, Any], account_id: UUID, *, ip: str
    ) -> dict[str, Any]:
        tenant = await self._tenant_for(actor)
        await self._account_row(tenant.schema_name, account_id)
        await self._bind(tenant.schema_name)
        result = await self._session.execute(
            text(
                f"""
                UPDATE accounts
                SET archived_at = now(), updated_at = now()
                WHERE id = :id AND archived_at IS NULL
                RETURNING {ACCOUNT_COLS}
                """
            ),
            {"id": account_id},
        )
        row = result.mappings().first()
        if row is None:
            raise _not_found()
        await self._audit.append(
            self._session,
            event_type="account.archived",
            actor_email=str(actor.get("email")),
            ip_address=ip,
            tenant_id=tenant.id,
            schema_name=tenant.schema_name,
            payload={"accountId": str(account_id)},
        )
        await self._session.commit()
        return _serialize_account(row)

    async def list_account_contacts(
        self, actor: dict[str, Any], account_id: UUID
    ) -> list[dict[str, Any]]:
        tenant = await self._tenant_for(actor)
        await self._account_row(tenant.schema_name, account_id)
        await self._bind(tenant.schema_name)
        result = await self._session.execute(
            text(
                f"""
                SELECT {CONTACT_COLS}
                FROM contacts
                WHERE account_id = :account_id AND archived_at IS NULL
                ORDER BY created_at DESC, id DESC
                """
            ),
            {"account_id": account_id},
        )
        return [_serialize_contact(row) for row in result.mappings()]

    # ---- contacts -------------------------------------------------------

    async def list_contacts(
        self,
        actor: dict[str, Any],
        *,
        q: str | None = None,
        account_id: UUID | None = None,
        cursor: str | None = None,
        limit: int | None = None,
    ) -> dict[str, Any]:
        tenant = await self._tenant_for(actor)
        await self._bind(tenant.schema_name)
        page_size = _clamp_limit(limit)
        result = await self._session.execute(
            text(
                f"""
                SELECT {CONTACT_COLS}
                FROM contacts
                WHERE archived_at IS NULL
                  AND (
                    CAST(:q AS text) IS NULL
                    OR lower(full_name) LIKE CAST(:q AS text)
                    OR lower(primary_email) LIKE CAST(:q AS text)
                  )
                  AND (
                    CAST(:account_id AS uuid) IS NULL
                    OR account_id = CAST(:account_id AS uuid)
                  )
                  AND (
                    CAST(:cursor_id AS uuid) IS NULL
                    OR (created_at, id) < (
                        SELECT c.created_at, c.id
                        FROM contacts c
                        WHERE c.id = CAST(:cursor_id AS uuid)
                    )
                  )
                ORDER BY created_at DESC, id DESC
                LIMIT :limit
                """
            ),
            {
                "q": f"%{q.lower()}%" if q else None,
                "account_id": account_id,
                "cursor_id": _cursor_uuid(cursor),
                "limit": page_size + 1,
            },
        )
        return self._page(result, _serialize_contact, page_size)

    async def create_contact(
        self,
        actor: dict[str, Any],
        *,
        full_name: str,
        account_id: UUID | None,
        job_title: str | None,
        primary_email: str | None,
        primary_phone: str | None,
        emails: list[Any] | None,
        phones: list[Any] | None,
        social: dict[str, Any] | None,
        address: str | None,
        notes: str | None,
        owner_user_id: UUID | None,
        ip: str,
    ) -> dict[str, Any]:
        tenant = await self._tenant_for(actor)
        await self._bind(tenant.schema_name)
        if account_id is not None:
            await self._require_active_account(account_id)
        contact_id = uuid4()
        result = await self._session.execute(
            text(
                f"""
                INSERT INTO contacts (
                    id, account_id, full_name, job_title, primary_email,
                    primary_phone, emails, phones, social, address, notes,
                    owner_user_id
                )
                VALUES (
                    :id, :account_id, :full_name, :job_title, :primary_email,
                    :primary_phone, CAST(:emails AS jsonb), CAST(:phones AS jsonb),
                    CAST(:social AS jsonb), :address, :notes, :owner_user_id
                )
                RETURNING {CONTACT_COLS}
                """
            ),
            {
                "id": contact_id,
                "account_id": account_id,
                "full_name": full_name,
                "job_title": job_title,
                "primary_email": primary_email,
                "primary_phone": primary_phone,
                "emails": json.dumps(emails or []),
                "phones": json.dumps(phones or []),
                "social": json.dumps(social or {}),
                "address": address,
                "notes": notes,
                "owner_user_id": owner_user_id,
            },
        )
        row = result.mappings().one()
        await self._audit.append(
            self._session,
            event_type="contact.created",
            actor_email=str(actor.get("email")),
            ip_address=ip,
            tenant_id=tenant.id,
            schema_name=tenant.schema_name,
            payload={"contactId": str(contact_id)},
        )
        await self._session.commit()
        return _serialize_contact(row)

    async def get_contact(
        self, actor: dict[str, Any], contact_id: UUID
    ) -> dict[str, Any]:
        tenant = await self._tenant_for(actor)
        row = await self._contact_row(tenant.schema_name, contact_id)
        return _serialize_contact(row)

    async def update_contact(
        self,
        actor: dict[str, Any],
        contact_id: UUID,
        *,
        changes: dict[str, Any],
        ip: str,
    ) -> dict[str, Any]:
        tenant = await self._tenant_for(actor)
        await self._contact_row(tenant.schema_name, contact_id)
        await self._bind(tenant.schema_name)
        assignments: list[str] = []
        params: dict[str, Any] = {"id": contact_id}
        for key in _CONTACT_TEXT_FIELDS:
            if key in changes:
                assignments.append(f"{key} = :{key}")
                params[key] = changes[key]
        for key in _CONTACT_JSON_FIELDS:
            if key in changes:
                assignments.append(f"{key} = CAST(:{key} AS jsonb)")
                params[key] = json.dumps(changes[key])
        if "account_id" in changes:
            new_account = changes["account_id"]
            if new_account is not None:
                await self._require_active_account(new_account)
            assignments.append("account_id = CAST(:account_id AS uuid)")
            params["account_id"] = new_account
        if not assignments:
            row = await self._contact_row(tenant.schema_name, contact_id)
            return _serialize_contact(row)
        result = await self._session.execute(
            text(
                f"""
                UPDATE contacts
                SET {", ".join(assignments)}, updated_at = now()
                WHERE id = :id AND archived_at IS NULL
                RETURNING {CONTACT_COLS}
                """
            ),
            params,
        )
        row = result.mappings().first()
        if row is None:
            raise _not_found()
        changed = [key for key in changes if key in (
            *_CONTACT_TEXT_FIELDS,
            *_CONTACT_JSON_FIELDS,
            "account_id",
        )]
        await self._audit.append(
            self._session,
            event_type="contact.updated",
            actor_email=str(actor.get("email")),
            ip_address=ip,
            tenant_id=tenant.id,
            schema_name=tenant.schema_name,
            payload={"contactId": str(contact_id), "changed": sorted(changed)},
        )
        await self._session.commit()
        return _serialize_contact(row)

    async def archive_contact(
        self, actor: dict[str, Any], contact_id: UUID, *, ip: str
    ) -> dict[str, Any]:
        tenant = await self._tenant_for(actor)
        await self._contact_row(tenant.schema_name, contact_id)
        await self._bind(tenant.schema_name)
        result = await self._session.execute(
            text(
                f"""
                UPDATE contacts
                SET archived_at = now(), updated_at = now()
                WHERE id = :id AND archived_at IS NULL
                RETURNING {CONTACT_COLS}
                """
            ),
            {"id": contact_id},
        )
        row = result.mappings().first()
        if row is None:
            raise _not_found()
        await self._audit.append(
            self._session,
            event_type="contact.archived",
            actor_email=str(actor.get("email")),
            ip_address=ip,
            tenant_id=tenant.id,
            schema_name=tenant.schema_name,
            payload={"contactId": str(contact_id)},
        )
        await self._session.commit()
        return _serialize_contact(row)

    async def record_consent(
        self,
        actor: dict[str, Any],
        contact_id: UUID,
        *,
        status: str,
        basis: str | None,
        ip: str,
    ) -> dict[str, Any]:
        if status == "granted" and not basis:
            raise _validation_error(
                "La base de tratamiento es obligatoria para otorgar consentimiento."
            )
        tenant = await self._tenant_for(actor)
        await self._contact_row(tenant.schema_name, contact_id)
        await self._bind(tenant.schema_name)
        result = await self._session.execute(
            text(
                f"""
                UPDATE contacts
                SET consent_status = :status,
                    consent_basis = :basis,
                    consent_recorded_at = now(),
                    updated_at = now()
                WHERE id = :id AND archived_at IS NULL
                RETURNING {CONTACT_COLS}
                """
            ),
            {"id": contact_id, "status": status, "basis": basis},
        )
        row = result.mappings().first()
        if row is None:
            raise _not_found()
        await self._audit.append(
            self._session,
            event_type="contact.consent.recorded",
            actor_email=str(actor.get("email")),
            ip_address=ip,
            tenant_id=tenant.id,
            schema_name=tenant.schema_name,
            payload={"contactId": str(contact_id), "status": status},
        )
        await self._session.commit()
        return _serialize_contact(row)

    async def assign_contact(
        self,
        actor: dict[str, Any],
        contact_id: UUID,
        *,
        owner_user_id: UUID | None,
        ip: str,
    ) -> dict[str, Any]:
        tenant = await self._tenant_for(actor)
        await self._contact_row(tenant.schema_name, contact_id)
        await self._bind(tenant.schema_name)
        result = await self._session.execute(
            text(
                f"""
                UPDATE contacts
                SET owner_user_id = :owner_user_id,
                    updated_at = now()
                WHERE id = :id AND archived_at IS NULL
                RETURNING {CONTACT_COLS}
                """
            ),
            {"id": contact_id, "owner_user_id": owner_user_id},
        )
        row = result.mappings().first()
        if row is None:
            raise _not_found()
        await self._audit.append(
            self._session,
            event_type="contact.assigned",
            actor_email=str(actor.get("email")),
            ip_address=ip,
            tenant_id=tenant.id,
            schema_name=tenant.schema_name,
            payload={
                "contactId": str(contact_id),
                "ownerUserId": (
                    str(owner_user_id) if owner_user_id is not None else None
                ),
            },
        )
        await self._session.commit()
        return _serialize_contact(row)

    # ---- helpers --------------------------------------------------------

    def _page(
        self, result: Any, serialize: Any, page_size: int
    ) -> dict[str, Any]:
        rows = list(result.mappings())
        next_cursor: str | None = None
        if len(rows) > page_size:
            rows = rows[:page_size]
            next_cursor = str(rows[-1]["id"])
        page: dict[str, Any] = {"items": [serialize(row) for row in rows]}
        if next_cursor is not None:
            page["nextCursor"] = next_cursor
        return page

    async def _account_row(self, schema_name: str, account_id: UUID) -> dict[str, Any]:
        await self._bind(schema_name)
        row = (
            await self._session.execute(
                text(
                    f"""
                    SELECT {ACCOUNT_COLS}
                    FROM accounts
                    WHERE id = :id AND archived_at IS NULL
                    """
                ),
                {"id": account_id},
            )
        ).mappings().first()
        if row is None:
            raise _not_found()
        return dict(row)

    async def _contact_row(self, schema_name: str, contact_id: UUID) -> dict[str, Any]:
        await self._bind(schema_name)
        row = (
            await self._session.execute(
                text(
                    f"""
                    SELECT {CONTACT_COLS}
                    FROM contacts
                    WHERE id = :id AND archived_at IS NULL
                    """
                ),
                {"id": contact_id},
            )
        ).mappings().first()
        if row is None:
            raise _not_found()
        return dict(row)

    async def _require_active_account(self, account_id: UUID) -> None:
        row = (
            await self._session.execute(
                text(
                    """
                    SELECT id FROM accounts
                    WHERE id = :id AND archived_at IS NULL
                    """
                ),
                {"id": account_id},
            )
        ).first()
        if row is None:
            raise _validation_error("La cuenta indicada no existe o está archivada.")

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
