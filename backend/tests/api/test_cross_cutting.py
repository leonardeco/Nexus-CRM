from httpx import AsyncClient

from tests.conftest import CSRF_HEADERS, enroll_admin, signup_payload, unique_email


_PROBLEM_FIELDS = {"type", "title", "status", "detail", "code"}


async def test_tc_x_1_mutating_requests_require_csrf_header(
    client: AsyncClient,
) -> None:
    rejected = await client.post("/api/v1/public/signups", json=signup_payload())
    assert rejected.status_code == 403
    assert rejected.json()["code"] == "csrf_rejected"
    assert rejected.headers["content-type"].startswith("application/problem+json")

    login_rejected = await client.post(
        "/api/v1/public/sessions",
        json={"email": unique_email(), "password": "ValidPass1x"},
    )
    assert login_rejected.status_code == 403
    assert login_rejected.json()["code"] == "csrf_rejected"

    allowed = await client.post(
        "/api/v1/public/signups", headers=CSRF_HEADERS, json=signup_payload()
    )
    assert allowed.status_code == 202


async def test_tc_x_3_signup_is_rate_limited(client: AsyncClient) -> None:
    for attempt in range(10):
        response = await client.post(
            "/api/v1/public/signups",
            headers=CSRF_HEADERS,
            json=signup_payload(),
        )
        assert response.status_code == 202, attempt
    eleventh = await client.post(
        "/api/v1/public/signups",
        headers=CSRF_HEADERS,
        json=signup_payload(),
    )
    assert eleventh.status_code == 429
    body = eleventh.json()
    assert body["code"] == "rate_limited"
    assert eleventh.headers["content-type"].startswith("application/problem+json")
    assert _PROBLEM_FIELDS <= set(body)


async def test_tc_x_4_errors_are_problem_json_and_success_is_camel_case(
    client: AsyncClient,
) -> None:
    validation = await client.post(
        "/api/v1/public/signups",
        headers=CSRF_HEADERS,
        json=signup_payload(password="short"),
    )
    assert validation.status_code == 422
    _assert_problem(validation)

    unknown = await client.post(
        "/api/v1/public/sessions",
        headers=CSRF_HEADERS,
        json={"email": unique_email(), "password": "WrongPass1x"},
    )
    assert unknown.status_code == 401
    _assert_problem(unknown)

    missing = await client.get("/api/v1/arco-requests")
    assert missing.status_code in {401, 403}
    _assert_problem(missing)

    slug = await client.post(
        "/api/v1/public/tenants/no-such-tenant/arco-requests",
        headers=CSRF_HEADERS,
        json={
            "requesterName": "Ana",
            "requesterEmail": unique_email(),
            "requestType": "acceso",
            "details": "Datos",
        },
    )
    assert slug.status_code == 404
    _assert_problem(slug)

    admin = await enroll_admin(client)
    taken = await client.post(
        "/api/v1/invites",
        headers=CSRF_HEADERS,
        json={
            "email": str(admin["signup"]["email"]),
            "role": "vendedor",
            "fullName": "Duplicado",
        },
    )
    assert taken.status_code == 409
    _assert_problem(taken)

    me = await client.get("/api/v1/me")
    assert me.status_code == 200
    body = me.json()
    assert "userId" in body
    assert "tenantId" in body
    assert "fullName" in body
    assert "user_id" not in body


def _assert_problem(response) -> None:
    assert response.headers["content-type"].startswith("application/problem+json")
    body = response.json()
    assert _PROBLEM_FIELDS <= set(body)
    assert body["status"] == response.status_code
    assert isinstance(body["type"], str)
    assert isinstance(body["code"], str)
