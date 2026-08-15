import asyncio
import base64
import json
import logging
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decrypt_bytes, encrypt_bytes, hash_token
from app.modules.emailing.mailer import send_email

log = logging.getLogger("nexus.outbox")
_MAX_ATTEMPTS = 8


@dataclass(frozen=True)
class OutboxMessage:
    id: UUID
    to_email: str
    template: str
    payload: dict
    tenant_id: UUID | None
    scheduled_at: datetime
    attempts: int


def _stored_payload(payload: dict, raw_token: str | None) -> dict:
    stored = {key: value for key, value in payload.items() if key != "token"}
    if raw_token is not None:
        stored["token_hash"] = hash_token(raw_token)
        stored["token_encrypted"] = base64.b64encode(
            encrypt_bytes(raw_token.encode("utf-8"))
        ).decode("ascii")
        stored["body"] = "Token: [redacted]"
    return stored


def raw_token_from_payload(payload: dict) -> str | None:
    encrypted = payload.get("token_encrypted")
    if not encrypted or not isinstance(encrypted, str):
        return None
    return decrypt_bytes(base64.b64decode(encrypted)).decode("utf-8")


async def enqueue(
    session: AsyncSession,
    *,
    to_email: str,
    template: str,
    payload: dict,
    tenant_id: UUID | None = None,
    raw_token: str | None = None,
) -> UUID:
    message_id = uuid4()
    stored = _stored_payload(payload, raw_token)
    await session.execute(
        text(
            """
            INSERT INTO catalog.email_outbox
                (id, tenant_id, to_email, template, payload)
            VALUES
                (:id, :tenant_id, :to_email, :template, CAST(:payload AS jsonb))
            """
        ),
        {
            "id": message_id,
            "tenant_id": tenant_id,
            "to_email": to_email,
            "template": template,
            "payload": json.dumps(stored),
        },
    )
    subject = str(stored.get("subject") or template)
    smtp_body = (
        f"Token: {raw_token}" if raw_token is not None else str(stored.get("body") or "")
    )
    try:
        await asyncio.to_thread(send_email, to_email, subject, smtp_body, template)
    except Exception:
        log.exception("smtp send failed for %s", message_id)
        await mark_failed(session, message_id, "smtp_failed")
        return message_id
    await mark_sent(session, message_id)
    return message_id


async def fetch_due(session: AsyncSession, *, limit: int = 50) -> list[OutboxMessage]:
    result = await session.execute(
        text(
            """
            SELECT id, to_email, template, payload, tenant_id, scheduled_at, attempts
            FROM catalog.email_outbox
            WHERE sent_at IS NULL
              AND scheduled_at <= now()
              AND attempts < :max_attempts
            ORDER BY scheduled_at
            LIMIT :limit
            """
        ),
        {"limit": limit, "max_attempts": _MAX_ATTEMPTS},
    )
    messages: list[OutboxMessage] = []
    for row in result.mappings():
        payload = row["payload"]
        if isinstance(payload, str):
            payload = json.loads(payload)
        messages.append(
            OutboxMessage(
                id=row["id"],
                to_email=row["to_email"],
                template=row["template"],
                payload=payload or {},
                tenant_id=row["tenant_id"],
                scheduled_at=row["scheduled_at"],
                attempts=row["attempts"],
            )
        )
    return messages


async def mark_sent(session: AsyncSession, message_id: UUID) -> None:
    await session.execute(
        text(
            """
            UPDATE catalog.email_outbox
            SET sent_at = now(),
                payload = (payload - 'token' - 'token_encrypted')
            WHERE id = :id
            """
        ),
        {"id": message_id},
    )


async def mark_failed(session: AsyncSession, message_id: UUID, error: str) -> None:
    await session.execute(
        text(
            """
            UPDATE catalog.email_outbox
            SET attempts = attempts + 1,
                last_error = :error
            WHERE id = :id
            """
        ),
        {"id": message_id, "error": error},
    )
