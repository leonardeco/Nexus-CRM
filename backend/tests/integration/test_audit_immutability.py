from urllib.parse import parse_qs, urlparse

import pyotp
from httpx import AsyncClient
from sqlalchemy import text

from app.db.engine import engine
from app.db.search_path import set_search_path
from tests.conftest import CSRF_HEADERS, VALID_PASSWORD, signup_payload


async def _outbox_token(email: str, template: str) -> str:
    async with engine.connect() as conn:
        payload = await conn.scalar(
            text(
                """
                SELECT payload FROM catalog.email_outbox
                WHERE lower(to_email) = lower(:email)
                  AND template = :template
                ORDER BY created_at DESC
                LIMIT 1
                """
            ),
            {"email": email, "template": template},
        )
    assert payload is not None
    if isinstance(payload, str):
        import json

        payload = json.loads(payload)
    return str(payload["token"])


async def _enroll_admin(client: AsyncClient) -> dict[str, object]:
    payload = signup_payload()
    created = await client.post(
        "/api/v1/public/signups", headers=CSRF_HEADERS, json=payload
    )
    assert created.status_code == 202
    token = await _outbox_token(str(payload["email"]), "verify_email")
    verified = await client.post(
        "/api/v1/public/email-verifications",
        headers=CSRF_HEADERS,
        json={"token": token},
    )
    assert verified.status_code == 204
    login = await client.post(
        "/api/v1/public/sessions",
        headers=CSRF_HEADERS,
        json={"email": payload["email"], "password": VALID_PASSWORD},
    )
    assert login.status_code == 200
    start = await client.post("/api/v1/me/mfa/totp", headers=CSRF_HEADERS)
    assert start.status_code == 200, start.text
    secret = parse_qs(urlparse(start.json()["otpauthUrl"]).query)["secret"][0]
    confirm = await client.post(
        "/api/v1/me/mfa/totp/confirm",
        headers=CSRF_HEADERS,
        json={"code": pyotp.TOTP(secret).now(), "backupCodesSaved": True},
    )
    assert confirm.status_code == 200
    me = await client.get("/api/v1/me")
    assert me.status_code == 200
    return {"signup": payload, "me": me.json()}


async def _schema_for(tenant_id: str) -> str:
    async with engine.connect() as conn:
        name = await conn.scalar(
            text("SELECT schema_name FROM catalog.tenants WHERE id = :id"),
            {"id": tenant_id},
        )
    assert name is not None
    return str(name)


async def test_tc_8_3_update_and_delete_leave_audit_row_unchanged(
    client: AsyncClient,
) -> None:
    admin = await _enroll_admin(client)
    schema_name = await _schema_for(str(admin["me"]["tenantId"]))
    async with engine.begin() as conn:
        await set_search_path(conn, schema_name)
        row = (
            await conn.execute(
                text(
                    """
                    SELECT id, event_type, actor_email, ip_address, occurred_at
                    FROM audit_events
                    ORDER BY occurred_at
                    LIMIT 1
                    """
                )
            )
        ).mappings().first()
        assert row is not None
        original = dict(row)
        await conn.execute(
            text("UPDATE audit_events SET event_type = :tampered WHERE id = :id"),
            {"id": original["id"], "tampered": "tampered"},
        )
        await conn.execute(
            text("DELETE FROM audit_events WHERE id = :id"),
            {"id": original["id"]},
        )
        after = (
            await conn.execute(
                text(
                    """
                    SELECT id, event_type, actor_email, ip_address
                    FROM audit_events
                    WHERE id = :id
                    """
                ),
                {"id": original["id"]},
            )
        ).mappings().first()
    assert after is not None
    assert after["event_type"] == original["event_type"]
    assert after["event_type"] != "tampered"
    assert after["actor_email"] == original["actor_email"]
