from urllib.parse import parse_qs, urlparse
from uuid import uuid4

import pyotp
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from app.db.engine import engine
from app.main import app
from tests.conftest import CSRF_HEADERS, VALID_PASSWORD, signup_payload, unique_email

_NOT_FOUND = {
    "type": "https://nexus.crm/problems/not_found",
    "title": "No encontrado",
    "status": 404,
    "detail": "No encontrado.",
    "code": "not_found",
}
_PUBLIC_TYPES = ("acceso", "rectificacion", "cancelacion", "oposicion")


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


def _public_body(**overrides: object) -> dict[str, object]:
    body: dict[str, object] = {
        "requesterName": "Carlos Titular",
        "requesterEmail": unique_email(),
        "requestType": "acceso",
        "details": "Solicito copia de mis datos.",
    }
    body.update(overrides)
    return body


async def test_tc_7_1_public_arco_creates_open_request(client: AsyncClient) -> None:
    admin = await _enroll_admin(client)
    slug = str(admin["me"]["tenantSlug"])
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as anon:
        created = await anon.post(
            f"/api/v1/public/tenants/{slug}/arco-requests",
            headers=CSRF_HEADERS,
            json=_public_body(requestType="acceso"),
        )
    assert created.status_code == 201
    body = created.json()
    assert body["source"] == "public_form"
    assert body["status"] == "open"
    assert body["requestType"] == "acceso"
    assert "nexus_session" not in created.cookies
    set_cookie = created.headers.get_list("set-cookie")
    assert all("nexus_session=" not in value for value in set_cookie)
    inbox = await client.get("/api/v1/arco-requests")
    assert inbox.status_code == 200
    assert any(item["id"] == body["id"] for item in inbox.json())


async def test_tc_7_1_all_four_request_types(client: AsyncClient) -> None:
    admin = await _enroll_admin(client)
    slug = str(admin["me"]["tenantSlug"])
    for request_type in _PUBLIC_TYPES:
        response = await client.post(
            f"/api/v1/public/tenants/{slug}/arco-requests",
            headers=CSRF_HEADERS,
            json=_public_body(requestType=request_type),
        )
        assert response.status_code == 201, request_type
        assert response.json()["requestType"] == request_type


async def test_public_arco_without_csrf_is_rejected(client: AsyncClient) -> None:
    admin = await _enroll_admin(client)
    slug = str(admin["me"]["tenantSlug"])
    response = await client.post(
        f"/api/v1/public/tenants/{slug}/arco-requests",
        json=_public_body(),
    )
    assert response.status_code == 403
    assert response.json()["code"] == "csrf_rejected"


async def test_tc_7_2_public_arco_rate_limited_per_slug_ip(client: AsyncClient) -> None:
    admin = await _enroll_admin(client)
    slug = str(admin["me"]["tenantSlug"])
    path = f"/api/v1/public/tenants/{slug}/arco-requests"
    for attempt in range(10):
        response = await client.post(path, headers=CSRF_HEADERS, json=_public_body())
        assert response.status_code == 201, attempt
    eleventh = await client.post(path, headers=CSRF_HEADERS, json=_public_body())
    assert eleventh.status_code == 429
    assert eleventh.headers["content-type"].startswith("application/problem+json")
    assert eleventh.json()["code"] == "rate_limited"


async def test_tc_7_3_unknown_slug_is_identical_not_found(client: AsyncClient) -> None:
    first = await client.post(
        "/api/v1/public/tenants/no-existe-slug/arco-requests",
        headers=CSRF_HEADERS,
        json=_public_body(),
    )
    second = await client.post(
        "/api/v1/public/tenants/otro-slug-falso/arco-requests",
        headers=CSRF_HEADERS,
        json=_public_body(),
    )
    assert first.status_code == 404
    assert second.status_code == 404
    assert first.headers["content-type"].startswith("application/problem+json")
    assert first.json() == _NOT_FOUND
    assert second.json() == first.json()


async def test_tc_7_4_admin_responds_then_closes(client: AsyncClient) -> None:
    admin = await _enroll_admin(client)
    slug = str(admin["me"]["tenantSlug"])
    created = await client.post(
        f"/api/v1/public/tenants/{slug}/arco-requests",
        headers=CSRF_HEADERS,
        json=_public_body(),
    )
    assert created.status_code == 201
    arco_id = created.json()["id"]
    responded = await client.post(
        f"/api/v1/arco-requests/{arco_id}/response",
        headers=CSRF_HEADERS,
        json={"responseText": "Adjunto la copia solicitada."},
    )
    assert responded.status_code == 200
    assert responded.json()["status"] == "responded"
    assert responded.json()["responseText"] == "Adjunto la copia solicitada."
    closed = await client.post(
        f"/api/v1/arco-requests/{arco_id}/closure",
        headers=CSRF_HEADERS,
        json={},
    )
    assert closed.status_code == 200
    assert closed.json()["status"] == "closed"
    assert closed.json()["responseText"] == "Adjunto la copia solicitada."


async def test_tc_7_5_self_arco_as_logged_in_user(client: AsyncClient) -> None:
    admin = await _enroll_admin(client)
    me = admin["me"]
    created = await client.post(
        "/api/v1/me/arco-requests",
        headers=CSRF_HEADERS,
        json={"requestType": "rectificacion", "details": "Corrijan mi nombre."},
    )
    assert created.status_code == 201
    body = created.json()
    assert body["source"] == "logged_in_self"
    assert body["status"] == "open"
    assert body["requestType"] == "rectificacion"
    assert body["requesterEmail"] == me["email"]
    assert body["requesterName"] == me["fullName"]
    inbox = await client.get("/api/v1/arco-requests")
    assert any(item["id"] == body["id"] for item in inbox.json())


async def test_tc_7_6_manual_mail_intake(client: AsyncClient) -> None:
    await _enroll_admin(client)
    created = await client.post(
        "/api/v1/arco-requests",
        headers=CSRF_HEADERS,
        json={
            "requestType": "cancelacion",
            "requesterName": "Luisa Correo",
            "requesterEmail": unique_email(),
            "details": "Solicitud recibida por correo.",
        },
    )
    assert created.status_code == 201
    body = created.json()
    assert body["source"] == "manual_mail"
    assert body["status"] == "open"
    inbox = await client.get("/api/v1/arco-requests")
    assert any(item["id"] == body["id"] for item in inbox.json())


async def test_tc_7_7_unauthenticated_cannot_use_inbox(client: AsyncClient) -> None:
    listed = await client.get("/api/v1/arco-requests")
    assert listed.status_code in {401, 403}
    assert listed.headers["content-type"].startswith("application/problem+json")
    fake_id = uuid4()
    responded = await client.post(
        f"/api/v1/arco-requests/{fake_id}/response",
        headers=CSRF_HEADERS,
        json={"responseText": "no"},
    )
    assert responded.status_code in {401, 403}
    closed = await client.post(
        f"/api/v1/arco-requests/{fake_id}/closure",
        headers=CSRF_HEADERS,
        json={},
    )
    assert closed.status_code in {401, 403}
