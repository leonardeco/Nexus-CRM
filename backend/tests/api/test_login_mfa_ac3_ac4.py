import re
from collections.abc import AsyncIterator
from urllib.parse import parse_qs, urlparse

import pyotp
from fakeredis import FakeAsyncRedis
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from app.db.engine import engine
from app.main import app
from app.modules.rbac.deps import get_redis
from tests.conftest import (
    CSRF_HEADERS,
    VALID_PASSWORD,
    enroll_admin,
    outbox_token,
    signup_and_verify,
    signup_payload,
    unique_email,
)

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
    me = await client.get("/api/v1/me")
    assert me.status_code == 200
    assert me.json()["scope"] == "full"
    tenant = await client.get("/api/v1/tenant")
    assert tenant.status_code == 200


def _no_session_cookie(response) -> None:
    assert "nexus_session" not in response.cookies
    set_cookie = response.headers.get_list("set-cookie")
    assert all("nexus_session=" not in value for value in set_cookie)


async def test_tc_3_1_verified_user_logs_in_with_session_cookie(
    client: AsyncClient,
) -> None:
    admin = await enroll_admin(client)
    await client.request("DELETE", "/api/v1/sessions/current", headers=CSRF_HEADERS)
    login = await client.post(
        "/api/v1/public/sessions",
        headers=CSRF_HEADERS,
        json={"email": admin["signup"]["email"], "password": VALID_PASSWORD},
    )
    assert login.status_code == 200
    assert login.json()["status"] == "mfa_required"
    challenge_id = login.json()["mfaChallengeId"]
    completed = await client.post(
        "/api/v1/public/sessions/mfa",
        headers=CSRF_HEADERS,
        json={
            "challengeId": challenge_id,
            "code": pyotp.TOTP(str(admin["secret"])).now(),
        },
    )
    assert completed.status_code == 200
    body = completed.json()
    assert body.get("scope") == "full"
    assert body.get("status") in {None, "authenticated"}
    assert "nexus_session" in completed.cookies
    set_cookie = ",".join(completed.headers.get_list("set-cookie"))
    assert "httponly" in set_cookie.lower()
    assert "samesite=lax" in set_cookie.lower()
    me = await client.get("/api/v1/me")
    assert me.status_code == 200
    assert me.json()["scope"] == "full"


async def test_tc_3_3_wrong_password_is_generic(client: AsyncClient) -> None:
    payload = signup_payload()
    await signup_and_verify(client, payload)
    known = await client.post(
        "/api/v1/public/sessions",
        headers=CSRF_HEADERS,
        json={"email": payload["email"], "password": "WrongPass1x"},
    )
    unknown = await client.post(
        "/api/v1/public/sessions",
        headers=CSRF_HEADERS,
        json={"email": unique_email(), "password": "WrongPass1x"},
    )
    assert known.status_code == 401
    assert unknown.status_code == 401
    assert known.json()["code"] == "invalid_credentials"
    assert unknown.json()["code"] == "invalid_credentials"
    assert known.json()["detail"] == unknown.json()["detail"]
    assert known.headers["content-type"].startswith("application/problem+json")
    _no_session_cookie(known)
    _no_session_cookie(unknown)


async def test_tc_3_4_password_recovery_via_email_reset(client: AsyncClient) -> None:
    payload = signup_payload()
    await signup_and_verify(client, payload)
    requested = await client.post(
        "/api/v1/public/password-resets",
        headers=CSRF_HEADERS,
        json={"email": payload["email"]},
    )
    assert requested.status_code == 202
    assert requested.content == b""
    token = await outbox_token(str(payload["email"]), "password_reset")
    async with engine.connect() as conn:
        digest = await conn.scalar(
            text(
                """
                SELECT token_hash FROM catalog.password_reset_tokens
                ORDER BY created_at DESC LIMIT 1
                """
            )
        )
    assert digest is not None
    assert token not in str(digest)
    assert len(str(digest)) == 64
    new_password = "NewValid12x"
    confirmed = await client.post(
        "/api/v1/public/password-resets/confirm",
        headers=CSRF_HEADERS,
        json={"token": token, "password": new_password},
    )
    assert confirmed.status_code == 204
    old_login = await client.post(
        "/api/v1/public/sessions",
        headers=CSRF_HEADERS,
        json={"email": payload["email"], "password": VALID_PASSWORD},
    )
    assert old_login.status_code == 401
    new_login = await client.post(
        "/api/v1/public/sessions",
        headers=CSRF_HEADERS,
        json={"email": payload["email"], "password": new_password},
    )
    assert new_login.status_code == 200
    assert new_login.json()["status"] == "mfa_enrollment_required"


async def test_tc_3_5_reset_request_does_not_enumerate_emails(
    client: AsyncClient,
) -> None:
    payload = signup_payload()
    await signup_and_verify(client, payload)
    existing = await client.post(
        "/api/v1/public/password-resets",
        headers=CSRF_HEADERS,
        json={"email": payload["email"]},
    )
    missing = await client.post(
        "/api/v1/public/password-resets",
        headers=CSRF_HEADERS,
        json={"email": unique_email()},
    )
    assert existing.status_code == 202
    assert missing.status_code == 202
    assert existing.content == missing.content == b""


async def test_tc_3_6_reset_token_is_single_use_and_expires(
    client: AsyncClient,
) -> None:
    payload = signup_payload()
    await signup_and_verify(client, payload)
    await client.post(
        "/api/v1/public/password-resets",
        headers=CSRF_HEADERS,
        json={"email": payload["email"]},
    )
    token = await outbox_token(str(payload["email"]), "password_reset")
    first = await client.post(
        "/api/v1/public/password-resets/confirm",
        headers=CSRF_HEADERS,
        json={"token": token, "password": "ResetOnce1x"},
    )
    assert first.status_code == 204
    reused = await client.post(
        "/api/v1/public/password-resets/confirm",
        headers=CSRF_HEADERS,
        json={"token": token, "password": "ResetTwice1x"},
    )
    assert reused.status_code == 400
    assert reused.json()["code"] == "invalid_token"

    await client.post(
        "/api/v1/public/password-resets",
        headers=CSRF_HEADERS,
        json={"email": payload["email"]},
    )
    expired_token = await outbox_token(str(payload["email"]), "password_reset")
    async with engine.begin() as conn:
        await conn.execute(
            text(
                """
                UPDATE catalog.password_reset_tokens
                SET expires_at = now() - interval '2 hours'
                WHERE consumed_at IS NULL
                """
            )
        )
    expired = await client.post(
        "/api/v1/public/password-resets/confirm",
        headers=CSRF_HEADERS,
        json={"token": expired_token, "password": "ExpiredPw1x"},
    )
    assert expired.status_code == 400
    assert expired.json()["code"] == "invalid_token"
    login = await client.post(
        "/api/v1/public/sessions",
        headers=CSRF_HEADERS,
        json={"email": payload["email"], "password": "ResetOnce1x"},
    )
    assert login.status_code == 200


async def test_tc_3_7_auth_fails_closed_when_redis_down(
    client: AsyncClient,
) -> None:
    async def _dead_redis() -> AsyncIterator[FakeAsyncRedis]:
        redis = FakeAsyncRedis(decode_responses=True)

        async def boom(*_args: object, **_kwargs: object) -> bool:
            raise ConnectionError("redis down")

        redis.ping = boom  # type: ignore[method-assign]
        try:
            yield redis
        finally:
            await redis.aclose()

    previous = app.dependency_overrides.get(get_redis)
    app.dependency_overrides[get_redis] = _dead_redis
    try:
        response = await client.post(
            "/api/v1/public/sessions",
            headers=CSRF_HEADERS,
            json={"email": unique_email(), "password": VALID_PASSWORD},
        )
    finally:
        if previous is not None:
            app.dependency_overrides[get_redis] = previous
        else:
            app.dependency_overrides.pop(get_redis, None)
    assert response.status_code == 503
    assert response.json()["code"] == "redis_unavailable"
    assert response.headers["content-type"].startswith("application/problem+json")
    _no_session_cookie(response)


async def test_tc_3_8_password_reset_is_rate_limited(client: AsyncClient) -> None:
    email = unique_email()
    body = {"email": email}
    for attempt in range(3):
        response = await client.post(
            "/api/v1/public/password-resets", headers=CSRF_HEADERS, json=body
        )
        assert response.status_code == 202, attempt
    fourth = await client.post(
        "/api/v1/public/password-resets", headers=CSRF_HEADERS, json=body
    )
    assert fourth.status_code == 429
    assert fourth.json()["code"] == "rate_limited"
    assert fourth.headers["content-type"].startswith("application/problem+json")


async def test_tc_4_2_backup_code_login_is_single_use(client: AsyncClient) -> None:
    admin = await enroll_admin(client)
    backup = str(admin["backupCodes"][0])
    await client.request("DELETE", "/api/v1/sessions/current", headers=CSRF_HEADERS)
    login = await client.post(
        "/api/v1/public/sessions",
        headers=CSRF_HEADERS,
        json={"email": admin["signup"]["email"], "password": VALID_PASSWORD},
    )
    challenge_id = login.json()["mfaChallengeId"]
    first = await client.post(
        "/api/v1/public/sessions/mfa",
        headers=CSRF_HEADERS,
        json={"challengeId": challenge_id, "code": backup},
    )
    assert first.status_code == 200
    assert "nexus_session" in first.cookies
    await client.request("DELETE", "/api/v1/sessions/current", headers=CSRF_HEADERS)
    login_again = await client.post(
        "/api/v1/public/sessions",
        headers=CSRF_HEADERS,
        json={"email": admin["signup"]["email"], "password": VALID_PASSWORD},
    )
    second = await client.post(
        "/api/v1/public/sessions/mfa",
        headers=CSRF_HEADERS,
        json={
            "challengeId": login_again.json()["mfaChallengeId"],
            "code": backup,
        },
    )
    assert second.status_code == 401
    assert second.json()["code"] == "mfa_invalid"
    _no_session_cookie(second)


async def test_tc_4_3_enroll_rejected_without_backup_codes_saved(
    client: AsyncClient,
) -> None:
    payload = signup_payload()
    await signup_and_verify(client, payload)
    await client.post(
        "/api/v1/public/sessions",
        headers=CSRF_HEADERS,
        json={"email": payload["email"], "password": VALID_PASSWORD},
    )
    start = await client.post("/api/v1/me/mfa/totp", headers=CSRF_HEADERS)
    secret = parse_qs(urlparse(start.json()["otpauthUrl"]).query)["secret"][0]
    omitted = await client.post(
        "/api/v1/me/mfa/totp/confirm",
        headers=CSRF_HEADERS,
        json={"code": pyotp.TOTP(secret).now()},
    )
    assert omitted.status_code == 422
    assert omitted.headers["content-type"].startswith("application/problem+json")
    false_saved = await client.post(
        "/api/v1/me/mfa/totp/confirm",
        headers=CSRF_HEADERS,
        json={"code": pyotp.TOTP(secret).now(), "backupCodesSaved": False},
    )
    assert false_saved.status_code == 422
    me = await client.get("/api/v1/me")
    assert me.json()["mfaStatus"] == "pending"
    assert "backupCodes" not in omitted.json()
    assert "backupCodes" not in false_saved.json()


async def test_tc_4_4_gerente_must_enroll_mfa(client: AsyncClient) -> None:
    admin = await enroll_admin(client)
    await _set_seat_cap(str(admin["me"]["tenantId"]), 3)
    email = unique_email()
    invited = await client.post(
        "/api/v1/invites",
        headers=CSRF_HEADERS,
        json={"email": email, "role": "gerente", "fullName": "Gabriela Gerente"},
    )
    assert invited.status_code == 201
    token = await outbox_token(email, "invite")
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as gerente:
        accepted = await gerente.post(
            "/api/v1/public/invites/accept",
            headers=CSRF_HEADERS,
            json={"token": token, "password": "InvitePass1x"},
        )
        assert accepted.status_code == 200
        await gerente.request(
            "DELETE", "/api/v1/sessions/current", headers=CSRF_HEADERS
        )
        login = await gerente.post(
            "/api/v1/public/sessions",
            headers=CSRF_HEADERS,
            json={"email": email, "password": "InvitePass1x"},
        )
        assert login.status_code == 200
        body = login.json()
        assert body["status"] == "mfa_enrollment_required"
        assert body["principal"]["scope"] == "mfa_enroll_only"
        me = await gerente.get("/api/v1/me")
        assert me.status_code == 200
        forbidden = await gerente.get("/api/v1/users")
        assert forbidden.status_code == 403
        allowed_logout = await gerente.request(
            "DELETE", "/api/v1/sessions/current", headers=CSRF_HEADERS
        )
        assert allowed_logout.status_code == 204


async def test_tc_4_5_vendedor_is_not_required_to_enroll_mfa(
    client: AsyncClient,
) -> None:
    await enroll_admin(client)
    email = unique_email()
    invited = await client.post(
        "/api/v1/invites",
        headers=CSRF_HEADERS,
        json={"email": email, "role": "vendedor", "fullName": "Victor Vendedor"},
    )
    assert invited.status_code == 201
    token = await outbox_token(email, "invite")
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as vendedor:
        accepted = await vendedor.post(
            "/api/v1/public/invites/accept",
            headers=CSRF_HEADERS,
            json={"token": token, "password": "InvitePass1x"},
        )
        assert accepted.status_code == 200
        await vendedor.request(
            "DELETE", "/api/v1/sessions/current", headers=CSRF_HEADERS
        )
        login = await vendedor.post(
            "/api/v1/public/sessions",
            headers=CSRF_HEADERS,
            json={"email": email, "password": "InvitePass1x"},
        )
        assert login.status_code == 200
        body = login.json()
        assert body["status"] == "authenticated"
        assert body["principal"]["mfaStatus"] == "not_required"
        assert body["principal"]["scope"] == "full"
        assert "nexus_session" in login.cookies
        me = await vendedor.get("/api/v1/me")
        assert me.status_code == 200


async def test_tc_4_6_mfa_required_does_not_issue_nexus_session(
    client: AsyncClient,
) -> None:
    admin = await enroll_admin(client)
    await client.request("DELETE", "/api/v1/sessions/current", headers=CSRF_HEADERS)
    login = await client.post(
        "/api/v1/public/sessions",
        headers=CSRF_HEADERS,
        json={"email": admin["signup"]["email"], "password": VALID_PASSWORD},
    )
    assert login.status_code == 200
    body = login.json()
    assert body["status"] == "mfa_required"
    assert body.get("mfaChallengeId")
    _no_session_cookie(login)
    completed = await client.post(
        "/api/v1/public/sessions/mfa",
        headers=CSRF_HEADERS,
        json={
            "challengeId": body["mfaChallengeId"],
            "code": pyotp.TOTP(str(admin["secret"])).now(),
        },
    )
    assert completed.status_code == 200
    assert "nexus_session" in completed.cookies


async def test_tc_4_7_invalid_totp_does_not_grant_session(client: AsyncClient) -> None:
    admin = await enroll_admin(client)
    await client.request("DELETE", "/api/v1/sessions/current", headers=CSRF_HEADERS)
    login = await client.post(
        "/api/v1/public/sessions",
        headers=CSRF_HEADERS,
        json={"email": admin["signup"]["email"], "password": VALID_PASSWORD},
    )
    wrong = await client.post(
        "/api/v1/public/sessions/mfa",
        headers=CSRF_HEADERS,
        json={"challengeId": login.json()["mfaChallengeId"], "code": "000000"},
    )
    assert wrong.status_code == 401
    assert wrong.json()["code"] == "mfa_invalid"
    assert wrong.headers["content-type"].startswith("application/problem+json")
    _no_session_cookie(wrong)


async def test_tc_4_8_enroll_only_scope_cannot_reach_admin_surfaces(
    client: AsyncClient,
) -> None:
    payload = signup_payload()
    await signup_and_verify(client, payload)
    login = await client.post(
        "/api/v1/public/sessions",
        headers=CSRF_HEADERS,
        json={"email": payload["email"], "password": VALID_PASSWORD},
    )
    assert login.json()["status"] == "mfa_enrollment_required"
    me = await client.get("/api/v1/me")
    assert me.status_code == 200
    start = await client.post("/api/v1/me/mfa/totp", headers=CSRF_HEADERS)
    assert start.status_code == 200
    for method, path in (
        ("GET", "/api/v1/tenant"),
        ("GET", "/api/v1/users"),
        ("GET", "/api/v1/arco-requests"),
        ("GET", "/api/v1/audit-events"),
    ):
        response = await client.request(method, path, headers=CSRF_HEADERS)
        assert response.status_code == 403, path
    invite = await client.post(
        "/api/v1/invites",
        headers=CSRF_HEADERS,
        json={
            "email": unique_email(),
            "role": "vendedor",
            "fullName": "No",
        },
    )
    assert invite.status_code == 403


async def _set_seat_cap(tenant_id: str, seat_cap: int) -> None:
    async with engine.begin() as conn:
        await conn.execute(
            text("UPDATE catalog.tenants SET seat_cap = :cap WHERE id = :id"),
            {"cap": seat_cap, "id": tenant_id},
        )
