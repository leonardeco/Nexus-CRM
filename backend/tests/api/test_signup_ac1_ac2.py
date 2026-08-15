from httpx import AsyncClient
from sqlalchemy import text

from app.db.engine import engine
from app.db.identifiers import SCHEMA_NAME_RE
from tests.conftest import (
    CSRF_HEADERS,
    VALID_PASSWORD,
    outbox_count,
    outbox_token,
    signup_payload,
)


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


async def test_tc_1_2_minimum_valid_password_is_accepted(client: AsyncClient) -> None:
    payload = signup_payload(password="ValidPas1x")
    assert len(str(payload["password"])) == 10
    response = await client.post(
        "/api/v1/public/signups", headers=CSRF_HEADERS, json=payload
    )
    assert response.status_code == 202
    tenants = await _tenants_for_email(str(payload["email"]))
    assert len(tenants) == 1
    assert tenants[0]["status"] == "pending_verification"
    assert tenants[0]["role"] == "administrador"


async def test_tc_1_4_email_verify_provisions_active_schema(
    client: AsyncClient,
) -> None:
    payload = signup_payload()
    created = await client.post(
        "/api/v1/public/signups", headers=CSRF_HEADERS, json=payload
    )
    assert created.status_code == 202
    token = await outbox_token(str(payload["email"]), "verify_email")
    verified = await client.post(
        "/api/v1/public/email-verifications",
        headers=CSRF_HEADERS,
        json={"token": token},
    )
    assert verified.status_code == 204
    tenants = await _tenants_for_email(str(payload["email"]))
    assert len(tenants) == 1
    tenant = tenants[0]
    assert tenant["status"] == "active"
    assert SCHEMA_NAME_RE.match(str(tenant["schema_name"]))
    assert await _schema_exists(str(tenant["schema_name"])) is True
    login = await client.post(
        "/api/v1/public/sessions",
        headers=CSRF_HEADERS,
        json={"email": payload["email"], "password": VALID_PASSWORD},
    )
    assert login.status_code == 200
    assert login.json()["status"] == "mfa_enrollment_required"


async def test_tc_1_6_weak_password_does_not_create_tenant(client: AsyncClient) -> None:
    for password in ("Short1a", "alllowercase1", "ALLUPPERCASE1", "NoDigitsHere"):
        payload = signup_payload(password=password)
        response = await client.post(
            "/api/v1/public/signups", headers=CSRF_HEADERS, json=payload
        )
        assert response.status_code == 422, password
        body = response.json()
        assert body["code"] == "validation_error"
        assert response.headers["content-type"].startswith("application/problem+json")
        assert await _tenants_for_email(str(payload["email"])) == []


async def test_tc_1_7_verify_token_is_single_use_and_expires(
    client: AsyncClient,
) -> None:
    payload = signup_payload()
    await client.post("/api/v1/public/signups", headers=CSRF_HEADERS, json=payload)
    token = await outbox_token(str(payload["email"]), "verify_email")
    first = await client.post(
        "/api/v1/public/email-verifications",
        headers=CSRF_HEADERS,
        json={"token": token},
    )
    assert first.status_code == 204
    reused = await client.post(
        "/api/v1/public/email-verifications",
        headers=CSRF_HEADERS,
        json={"token": token},
    )
    assert reused.status_code == 400
    assert reused.json()["code"] == "invalid_token"
    assert reused.headers["content-type"].startswith("application/problem+json")

    expired_payload = signup_payload()
    await client.post(
        "/api/v1/public/signups", headers=CSRF_HEADERS, json=expired_payload
    )
    expired_token = await outbox_token(str(expired_payload["email"]), "verify_email")
    async with engine.begin() as conn:
        await conn.execute(
            text(
                """
                UPDATE catalog.email_verify_tokens t
                SET expires_at = now() - interval '1 hour'
                FROM catalog.users u
                JOIN catalog.email_identities e ON e.user_id = u.id
                WHERE t.user_id = u.id
                  AND lower(e.email) = lower(:email)
                  AND t.consumed_at IS NULL
                """
            ),
            {"email": expired_payload["email"]},
        )
    expired = await client.post(
        "/api/v1/public/email-verifications",
        headers=CSRF_HEADERS,
        json={"token": expired_token},
    )
    assert expired.status_code == 400
    assert expired.json()["code"] == "invalid_token"
    tenants = await _tenants_for_email(str(expired_payload["email"]))
    assert tenants[0]["status"] == "pending_verification"


async def test_tc_1_8_resend_verification_is_generic(client: AsyncClient) -> None:
    payload = signup_payload()
    await client.post("/api/v1/public/signups", headers=CSRF_HEADERS, json=payload)
    email = str(payload["email"])
    pending = await client.post(
        "/api/v1/public/email-verifications/resend",
        headers=CSRF_HEADERS,
        json={"email": email},
    )
    unknown = await client.post(
        "/api/v1/public/email-verifications/resend",
        headers=CSRF_HEADERS,
        json={"email": "nobody-resend@example.com"},
    )
    assert pending.status_code == 202
    assert pending.content == b""
    assert unknown.status_code == 202
    assert unknown.content == b""
    assert await outbox_count(email, "verify_email") == 2
    assert await outbox_count("nobody-resend@example.com", "verify_email") == 0


async def test_tc_2_1_signup_stores_consent_evidence(client: AsyncClient) -> None:
    payload = signup_payload()
    response = await client.post(
        "/api/v1/public/signups",
        headers={**CSRF_HEADERS, "X-Forwarded-For": "203.0.113.10"},
        json=payload,
    )
    assert response.status_code == 202
    async with engine.connect() as conn:
        row = (
            await conn.execute(
                text(
                    """
                    SELECT c.policy_version, c.ip_address, c.recorded_at,
                           c.accept_privacy_policy, c.accept_habeas_data
                    FROM catalog.consent_records c
                    JOIN catalog.email_identities e ON e.user_id = c.user_id
                    WHERE lower(e.email) = lower(:email)
                    """
                ),
                {"email": payload["email"]},
            )
        ).mappings().first()
    assert row is not None
    assert row["policy_version"] == "privacy-2026-08-01"
    assert row["ip_address"] == "203.0.113.10"
    assert row["recorded_at"] is not None
    assert row["accept_privacy_policy"] is True
    assert row["accept_habeas_data"] is True


async def test_tc_2_2_stored_policy_version_matches_submitted(
    client: AsyncClient,
) -> None:
    payload = signup_payload(policyVersion="privacy-2026-08-01")
    response = await client.post(
        "/api/v1/public/signups", headers=CSRF_HEADERS, json=payload
    )
    assert response.status_code == 202
    async with engine.connect() as conn:
        version = await conn.scalar(
            text(
                """
                SELECT c.policy_version
                FROM catalog.consent_records c
                JOIN catalog.email_identities e ON e.user_id = c.user_id
                WHERE lower(e.email) = lower(:email)
                """
            ),
            {"email": payload["email"]},
        )
    assert version == payload["policyVersion"]
    assert version != ""
