import re
from urllib.parse import parse_qs, urlparse

import pyotp
from httpx import AsyncClient
from sqlalchemy import text

from app.db.engine import engine
from tests.conftest import CSRF_HEADERS, VALID_PASSWORD, signup_payload, unique_email

_BACKUP_RE = re.compile(r"^[A-Z0-9]{8}$")


async def _verify_token_for(email: str) -> str:
    async with engine.connect() as conn:
        payload = await conn.scalar(
            text(
                """
                SELECT payload FROM catalog.email_outbox
                WHERE lower(to_email) = lower(:email)
                  AND template = 'verify_email'
                ORDER BY created_at DESC
                LIMIT 1
                """
            ),
            {"email": email},
        )
    assert payload is not None
    if isinstance(payload, str):
        import json

        payload = json.loads(payload)
    return str(payload["token"])


async def _signup_and_verify(client: AsyncClient, payload: dict[str, object]) -> None:
    created = await client.post(
        "/api/v1/public/signups", headers=CSRF_HEADERS, json=payload
    )
    assert created.status_code == 202
    token = await _verify_token_for(str(payload["email"]))
    verified = await client.post(
        "/api/v1/public/email-verifications",
        headers=CSRF_HEADERS,
        json={"token": token},
    )
    assert verified.status_code == 204


async def test_tc_3_2_sixth_failed_login_is_rate_limited(client: AsyncClient) -> None:
    email = unique_email()
    login = {"email": email, "password": "WrongPass1x"}
    for attempt in range(5):
        response = await client.post(
            "/api/v1/public/sessions", headers=CSRF_HEADERS, json=login
        )
        assert response.status_code == 401, attempt
        assert response.json()["code"] == "invalid_credentials"
    sixth = await client.post(
        "/api/v1/public/sessions", headers=CSRF_HEADERS, json=login
    )
    assert sixth.status_code == 429
    assert sixth.json()["code"] == "rate_limited"
    assert sixth.headers["content-type"].startswith("application/problem+json")


async def test_tc_4_1_admin_login_enrolls_totp_and_backup_codes(
    client: AsyncClient,
) -> None:
    payload = signup_payload()
    await _signup_and_verify(client, payload)

    login = await client.post(
        "/api/v1/public/sessions",
        headers=CSRF_HEADERS,
        json={"email": payload["email"], "password": VALID_PASSWORD},
    )
    assert login.status_code == 200
    body = login.json()
    assert body["status"] == "mfa_enrollment_required"
    assert "nexus_session" in login.cookies

    start = await client.post("/api/v1/me/mfa/totp", headers=CSRF_HEADERS)
    assert start.status_code == 200
    otpauth_url = start.json()["otpauthUrl"]
    secret = parse_qs(urlparse(otpauth_url).query)["secret"][0]
    code = pyotp.TOTP(secret).now()

    confirm = await client.post(
        "/api/v1/me/mfa/totp/confirm",
        headers=CSRF_HEADERS,
        json={"code": code, "backupCodesSaved": True},
    )
    assert confirm.status_code == 200
    codes = confirm.json()["backupCodes"]
    assert len(codes) == 10
    assert all(_BACKUP_RE.fullmatch(item) for item in codes)
