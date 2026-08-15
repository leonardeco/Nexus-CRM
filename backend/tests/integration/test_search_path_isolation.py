from urllib.parse import parse_qs, urlparse

import pytest
import pyotp
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from app.db.engine import engine
from app.db.identifiers import SCHEMA_NAME_RE
from app.db.search_path import set_search_path
from app.main import app
from tests.conftest import CSRF_HEADERS, VALID_PASSWORD, signup_payload, unique_email
from tests.conftest import outbox_token as _outbox_token


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


async def _tenant_schema(tenant_id: str) -> str:
    async with engine.connect() as conn:
        row = (
            await conn.execute(
                text(
                    """
                    SELECT schema_name, slug
                    FROM catalog.tenants
                    WHERE id = :id
                    """
                ),
                {"id": tenant_id},
            )
        ).mappings().first()
    assert row is not None
    name = str(row["schema_name"])
    assert SCHEMA_NAME_RE.match(name)
    return name


async def test_search_path_rejects_slug_and_catalog() -> None:
    async with engine.begin() as conn:
        with pytest.raises(ValueError):
            await set_search_path(conn, "catalog")
        with pytest.raises(ValueError):
            await set_search_path(conn, "public")
        with pytest.raises(ValueError):
            await set_search_path(conn, "acme-tenant")
        with pytest.raises(ValueError):
            await set_search_path(conn, "t_not_a_valid_hex_name")


async def test_tc_x_2_tenant_a_cannot_read_tenant_b_schema(client: AsyncClient) -> None:
    admin_a = await _enroll_admin(client)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client_b:
        admin_b = await _enroll_admin(client_b)
        slug_b = str(admin_b["me"]["tenantSlug"])
        created_b = await client_b.post(
            f"/api/v1/public/tenants/{slug_b}/arco-requests",
            headers=CSRF_HEADERS,
            json={
                "requesterName": "Titular B",
                "requesterEmail": unique_email(),
                "requestType": "acceso",
                "details": "Datos del tenant B.",
            },
        )
        assert created_b.status_code == 201
        b_arco_id = created_b.json()["id"]
        listed_b = await client_b.get("/api/v1/arco-requests")
        assert listed_b.status_code == 200
        assert any(item["id"] == b_arco_id for item in listed_b.json())
        audit_b = await client_b.get("/api/v1/audit-events")
        assert audit_b.status_code == 200
        b_audit_ids = {item["id"] for item in audit_b.json()["items"]}

    slug_a = str(admin_a["me"]["tenantSlug"])
    created_a = await client.post(
        f"/api/v1/public/tenants/{slug_a}/arco-requests",
        headers=CSRF_HEADERS,
        json={
            "requesterName": "Titular A",
            "requesterEmail": unique_email(),
            "requestType": "acceso",
            "details": "Datos del tenant A.",
        },
    )
    assert created_a.status_code == 201
    listed_a = await client.get("/api/v1/arco-requests")
    assert listed_a.status_code == 200
    a_ids = {item["id"] for item in listed_a.json()}
    assert created_a.json()["id"] in a_ids
    assert b_arco_id not in a_ids
    audit_a = await client.get("/api/v1/audit-events")
    assert audit_a.status_code == 200
    a_audit_ids = {item["id"] for item in audit_a.json()["items"]}
    assert a_audit_ids.isdisjoint(b_audit_ids)

    schema_a = await _tenant_schema(str(admin_a["me"]["tenantId"]))
    schema_b = await _tenant_schema(str(admin_b["me"]["tenantId"]))
    assert schema_a != schema_b
    async with engine.begin() as conn:
        await set_search_path(conn, schema_a)
        a_rows = (
            await conn.execute(text("SELECT id FROM arco_requests"))
        ).scalars().all()
        a_ids_sql = {str(value) for value in a_rows}
        assert str(created_a.json()["id"]) in a_ids_sql
        assert b_arco_id not in a_ids_sql
        with pytest.raises(ValueError):
            await set_search_path(conn, slug_b)
