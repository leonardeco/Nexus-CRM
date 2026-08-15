from httpx import AsyncClient
from sqlalchemy import text

from app.db.engine import engine
from tests.conftest import CSRF_HEADERS, VALID_PASSWORD, signup_payload


async def _tenants_for_email(email: str) -> list[dict]:
    async with engine.connect() as conn:
        result = await conn.execute(
            text(
                """
                SELECT t.id, t.slug, t.plan, t.seat_cap, t.status, t.schema_name, u.role
                FROM catalog.tenants t
                JOIN catalog.users u ON u.tenant_id = t.id
                JOIN catalog.email_identities e ON e.user_id = u.id
                WHERE lower(e.email) = lower(:email)
                """
            ),
            {"email": email},
        )
        return [dict(row) for row in result.mappings()]


async def _schema_exists(schema_name: str) -> bool:
    async with engine.connect() as conn:
        found = await conn.scalar(
            text("SELECT 1 FROM pg_namespace WHERE nspname = :name"),
            {"name": schema_name},
        )
        return found is not None


async def _outbox_count(email: str) -> int:
    async with engine.connect() as conn:
        count = await conn.scalar(
            text(
                """
                SELECT count(*) FROM catalog.email_outbox
                WHERE lower(to_email) = lower(:email)
                  AND template = 'verify_email'
                """
            ),
            {"email": email},
        )
        return int(count or 0)


async def test_signup_without_csrf_header_rejected(client: AsyncClient) -> None:
    response = await client.post("/api/v1/public/signups", json=signup_payload())
    assert response.status_code == 403
    body = response.json()
    assert body["code"] == "csrf_rejected"
    assert response.headers["content-type"].startswith("application/problem+json")


async def test_tc_1_1_signup_creates_pending_starter_tenant(client: AsyncClient) -> None:
    payload = signup_payload()
    response = await client.post(
        "/api/v1/public/signups", headers=CSRF_HEADERS, json=payload
    )
    assert response.status_code == 202
    assert response.content == b""

    tenants = await _tenants_for_email(str(payload["email"]))
    assert len(tenants) == 1
    tenant = tenants[0]
    assert tenant["plan"] == "starter"
    assert tenant["seat_cap"] == 2
    assert tenant["status"] == "pending_verification"
    assert tenant["role"] == "administrador"
    assert await _schema_exists(tenant["schema_name"]) is False
    assert await _outbox_count(str(payload["email"])) == 1


async def test_tc_2_3_missing_consent_does_not_create_tenant(client: AsyncClient) -> None:
    payload = signup_payload(acceptPrivacyPolicy=False, acceptHabeasData=True)
    response = await client.post(
        "/api/v1/public/signups", headers=CSRF_HEADERS, json=payload
    )
    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "validation_error"
    assert response.headers["content-type"].startswith("application/problem+json")
    assert await _tenants_for_email(str(payload["email"])) == []


async def test_tc_1_5_existing_email_still_202_one_tenant(client: AsyncClient) -> None:
    first = signup_payload()
    email = str(first["email"])
    created = await client.post(
        "/api/v1/public/signups", headers=CSRF_HEADERS, json=first
    )
    assert created.status_code == 202

    duplicate = signup_payload(email=email, slug="other-company-slug")
    again = await client.post(
        "/api/v1/public/signups", headers=CSRF_HEADERS, json=duplicate
    )
    assert again.status_code == 202
    assert again.content == b""
    assert len(await _tenants_for_email(email)) == 1
    assert await _outbox_count(email) == 1


async def test_tc_1_3_login_before_verify_is_forbidden(client: AsyncClient) -> None:
    payload = signup_payload()
    await client.post("/api/v1/public/signups", headers=CSRF_HEADERS, json=payload)

    response = await client.post(
        "/api/v1/public/sessions",
        headers=CSRF_HEADERS,
        json={"email": payload["email"], "password": VALID_PASSWORD},
    )
    assert response.status_code == 403
    body = response.json()
    assert body["code"] == "email_not_verified"
    assert response.headers["content-type"].startswith("application/problem+json")
    assert "nexus_session" not in response.cookies
    set_cookie = response.headers.get_list("set-cookie")
    assert all("nexus_session=" not in value for value in set_cookie)

    tenants = await _tenants_for_email(str(payload["email"]))
    assert tenants[0]["status"] == "pending_verification"
