from urllib.parse import parse_qs, urlparse

import pyotp
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from app.db.engine import engine
from app.main import app
from tests.conftest import CSRF_HEADERS, VALID_PASSWORD, signup_payload, unique_email

_REQUIRED_EVENTS = {
    "tenant.signup",
    "auth.login.success",
    "auth.login.failure",
    "users.invite.created",
    "users.invite.accepted",
    "users.role.changed",
    "users.deactivated",
    "consent.recorded",
    "arco.created",
    "arco.responded",
    "arco.closed",
}


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
    failed = await client.post(
        "/api/v1/public/sessions",
        headers=CSRF_HEADERS,
        json={"email": payload["email"], "password": "WrongPass1x"},
    )
    assert failed.status_code == 401
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
    return {"signup": payload, "me": me.json(), "secret": secret}


async def _set_seat_cap(tenant_id: str, seat_cap: int) -> None:
    async with engine.begin() as conn:
        await conn.execute(
            text("UPDATE catalog.tenants SET seat_cap = :cap WHERE id = :id"),
            {"cap": seat_cap, "id": tenant_id},
        )


async def test_tc_8_1_required_audit_events_are_listed(client: AsyncClient) -> None:
    admin = await _enroll_admin(client)
    me = admin["me"]
    tenant_id = str(me["tenantId"])
    slug = str(me["tenantSlug"])
    await _set_seat_cap(tenant_id, 3)
    invite_email = unique_email()
    invited = await client.post(
        "/api/v1/invites",
        headers=CSRF_HEADERS,
        json={
            "email": invite_email,
            "role": "vendedor",
            "fullName": "Victor Vendedor",
        },
    )
    assert invited.status_code == 201
    token = await _outbox_token(invite_email, "invite")
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as teammate:
        accepted = await teammate.post(
            "/api/v1/public/invites/accept",
            headers=CSRF_HEADERS,
            json={"token": token, "password": "InvitePass1x"},
        )
        assert accepted.status_code == 200
        teammate_id = accepted.json()["userId"]
    changed = await client.patch(
        f"/api/v1/users/{teammate_id}/role",
        headers=CSRF_HEADERS,
        json={"role": "gerente"},
    )
    assert changed.status_code == 200
    deactivated = await client.post(
        f"/api/v1/users/{teammate_id}/deactivation",
        headers=CSRF_HEADERS,
    )
    assert deactivated.status_code == 200
    created = await client.post(
        f"/api/v1/public/tenants/{slug}/arco-requests",
        headers=CSRF_HEADERS,
        json={
            "requesterName": "Carlos Titular",
            "requesterEmail": unique_email(),
            "requestType": "oposicion",
            "details": "No usen mis datos para marketing.",
        },
    )
    assert created.status_code == 201
    arco_id = created.json()["id"]
    responded = await client.post(
        f"/api/v1/arco-requests/{arco_id}/response",
        headers=CSRF_HEADERS,
        json={"responseText": "Registramos tu oposicion."},
    )
    assert responded.status_code == 200
    closed = await client.post(
        f"/api/v1/arco-requests/{arco_id}/closure",
        headers=CSRF_HEADERS,
        json={},
    )
    assert closed.status_code == 200
    listed = await client.get("/api/v1/audit-events")
    assert listed.status_code == 200
    page = listed.json()
    items = page["items"]
    types = {item["eventType"] for item in items}
    assert _REQUIRED_EVENTS <= types
    for item in items:
        assert "id" in item
        assert "occurredAt" in item
        assert "eventType" in item
        assert "ipAddress" in item


async def test_tc_8_2_audit_pagination_limit(client: AsyncClient) -> None:
    admin = await _enroll_admin(client)
    tenant_id = str(admin["me"]["tenantId"])
    async with engine.begin() as conn:
        for _ in range(60):
            await conn.execute(
                text(
                    """
                    INSERT INTO catalog.platform_audit_events
                        (event_type, actor_email, ip_address, tenant_id, payload)
                    VALUES
                        ('arco.created', :email, '127.0.0.1', :tenant_id, CAST(:payload AS jsonb))
                    """
                ),
                {
                    "email": admin["signup"]["email"],
                    "tenant_id": tenant_id,
                    "payload": "{}",
                },
            )
    first = await client.get("/api/v1/audit-events", params={"limit": 50})
    assert first.status_code == 200
    body = first.json()
    assert len(body["items"]) == 50
    assert body.get("nextCursor")
    second = await client.get(
        "/api/v1/audit-events",
        params={"limit": 50, "cursor": body["nextCursor"]},
    )
    assert second.status_code == 200
    assert len(second.json()["items"]) >= 1
    capped = await client.get("/api/v1/audit-events", params={"limit": 100})
    assert capped.status_code == 200
    assert len(capped.json()["items"]) <= 100
    over = await client.get("/api/v1/audit-events", params={"limit": 101})
    assert over.status_code == 422
    assert over.json()["code"] == "validation_error"


async def test_tc_8_4_secrets_are_not_in_audit_payloads(client: AsyncClient) -> None:
    admin = await _enroll_admin(client)
    listed = await client.get("/api/v1/audit-events")
    assert listed.status_code == 200
    blob = str(listed.json())
    assert VALID_PASSWORD not in blob
    assert "WrongPass1x" not in blob
    async with engine.connect() as conn:
        rows = (
            await conn.execute(
                text(
                    """
                    SELECT payload::text, actor_email
                    FROM catalog.platform_audit_events
                    WHERE tenant_id = :tenant_id
                    """
                ),
                {"tenant_id": str(admin["me"]["tenantId"])},
            )
        ).all()
    joined = " ".join(f"{row[0]} {row[1]}" for row in rows)
    assert VALID_PASSWORD not in joined
    assert "otpauth://" not in joined


async def test_tc_8_5_login_failure_is_audited(client: AsyncClient) -> None:
    payload = signup_payload()
    created = await client.post(
        "/api/v1/public/signups", headers=CSRF_HEADERS, json=payload
    )
    assert created.status_code == 202
    failed = await client.post(
        "/api/v1/public/sessions",
        headers=CSRF_HEADERS,
        json={"email": payload["email"], "password": "WrongPass1x"},
    )
    assert failed.status_code == 401
    async with engine.connect() as conn:
        row = (
            await conn.execute(
                text(
                    """
                    SELECT event_type, actor_email, ip_address, occurred_at, payload::text
                    FROM catalog.platform_audit_events
                    WHERE event_type = 'auth.login.failure'
                      AND lower(actor_email) = lower(:email)
                    ORDER BY occurred_at DESC
                    LIMIT 1
                    """
                ),
                {"email": payload["email"]},
            )
        ).mappings().first()
    assert row is not None
    assert row["ip_address"]
    assert row["occurred_at"] is not None
    assert "WrongPass1x" not in str(row["payload"])


async def test_tc_8_6_arco_status_changes_are_audited(client: AsyncClient) -> None:
    admin = await _enroll_admin(client)
    slug = str(admin["me"]["tenantSlug"])
    created = await client.post(
        f"/api/v1/public/tenants/{slug}/arco-requests",
        headers=CSRF_HEADERS,
        json={
            "requesterName": "Carlos Titular",
            "requesterEmail": unique_email(),
            "requestType": "acceso",
            "details": "Copia de datos.",
        },
    )
    assert created.status_code == 201
    arco_id = created.json()["id"]
    await client.post(
        f"/api/v1/arco-requests/{arco_id}/response",
        headers=CSRF_HEADERS,
        json={"responseText": "Listo."},
    )
    await client.post(
        f"/api/v1/arco-requests/{arco_id}/closure",
        headers=CSRF_HEADERS,
        json={},
    )
    listed = await client.get("/api/v1/audit-events")
    assert listed.status_code == 200
    types = {item["eventType"] for item in listed.json()["items"]}
    assert "arco.created" in types
    assert "arco.responded" in types
    assert "arco.closed" in types


async def test_audit_list_is_admin_only(client: AsyncClient) -> None:
    listed = await client.get("/api/v1/audit-events")
    assert listed.status_code in {401, 403}
