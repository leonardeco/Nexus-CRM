from uuid import uuid4

from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from app.db.engine import engine
from app.main import app
from tests.conftest import (
    CSRF_HEADERS,
    VALID_PASSWORD,
    enroll_admin,
    signup_and_verify,
    signup_payload,
    unique_email,
)
from tests.conftest import outbox_token as _outbox_token

_INVITE_PASSWORD = "InvitePass1x"


async def _new_client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def _set_seat_cap(tenant_id: str, seat_cap: int) -> None:
    async with engine.begin() as conn:
        await conn.execute(
            text("UPDATE catalog.tenants SET seat_cap = :cap WHERE id = :id"),
            {"cap": seat_cap, "id": tenant_id},
        )


async def _audit_types(client: AsyncClient) -> set[str]:
    listed = await client.get("/api/v1/audit-events")
    assert listed.status_code == 200, listed.text
    return {item["eventType"] for item in listed.json()["items"]}


async def _enroll_vendedor(admin: AsyncClient, tenant_id: str) -> AsyncClient:
    await _set_seat_cap(tenant_id, 5)
    email = unique_email()
    invited = await admin.post(
        "/api/v1/invites",
        headers=CSRF_HEADERS,
        json={"email": email, "role": "vendedor", "fullName": "Vera Vendedora"},
    )
    assert invited.status_code == 201, invited.text
    token = await _outbox_token(email, "invite")
    vendedor = await _new_client()
    accepted = await vendedor.post(
        "/api/v1/public/invites/accept",
        headers=CSRF_HEADERS,
        json={"token": token, "password": _INVITE_PASSWORD},
    )
    assert accepted.status_code == 200, accepted.text
    return vendedor


async def _create_account(client: AsyncClient, **overrides: object) -> dict:
    body: dict[str, object] = {"name": "Acme Corp"}
    body.update(overrides)
    created = await client.post("/api/v1/accounts", headers=CSRF_HEADERS, json=body)
    assert created.status_code == 201, created.text
    return created.json()


async def _create_contact(client: AsyncClient, **overrides: object) -> dict:
    body: dict[str, object] = {"fullName": "Maria Lopez"}
    body.update(overrides)
    created = await client.post("/api/v1/contacts", headers=CSRF_HEADERS, json=body)
    assert created.status_code == 201, created.text
    return created.json()


# ---- accounts (RF-002) --------------------------------------------------


async def test_tc_b_1_create_account_is_listed(client: AsyncClient) -> None:
    await enroll_admin(client)
    account = await _create_account(client, name="Globex")
    assert account["name"] == "Globex"
    listed = await client.get("/api/v1/accounts")
    assert listed.status_code == 200
    ids = [item["id"] for item in listed.json()["items"]]
    assert account["id"] in ids


async def test_tc_b_2_patch_account_reflects_and_audits(client: AsyncClient) -> None:
    await enroll_admin(client)
    account = await _create_account(client)
    patched = await client.patch(
        f"/api/v1/accounts/{account['id']}",
        headers=CSRF_HEADERS,
        json={"industry": "Software", "region": "LATAM"},
    )
    assert patched.status_code == 200
    body = patched.json()
    assert body["industry"] == "Software"
    assert body["region"] == "LATAM"
    fetched = await client.get(f"/api/v1/accounts/{account['id']}")
    assert fetched.json()["industry"] == "Software"
    assert "account.updated" in await _audit_types(client)


async def test_tc_b_3_archive_account_hides_and_audits(client: AsyncClient) -> None:
    await enroll_admin(client)
    account = await _create_account(client)
    archived = await client.post(
        f"/api/v1/accounts/{account['id']}/archive", headers=CSRF_HEADERS
    )
    assert archived.status_code == 200
    listed = await client.get("/api/v1/accounts")
    assert account["id"] not in [item["id"] for item in listed.json()["items"]]
    fetched = await client.get(f"/api/v1/accounts/{account['id']}")
    assert fetched.status_code == 404
    assert fetched.json()["code"] == "not_found"
    assert "account.archived" in await _audit_types(client)


async def test_tc_b_4_account_contacts_returns_active(client: AsyncClient) -> None:
    await enroll_admin(client)
    account = await _create_account(client)
    first = await _create_contact(
        client, fullName="Ana Uno", accountId=account["id"]
    )
    second = await _create_contact(
        client, fullName="Beto Dos", accountId=account["id"]
    )
    listed = await client.get(f"/api/v1/accounts/{account['id']}/contacts")
    assert listed.status_code == 200
    ids = {item["id"] for item in listed.json()}
    assert {first["id"], second["id"]} <= ids


# ---- contacts (RF-001) --------------------------------------------------


async def test_tc_b_5_create_contact_links_account_and_audits(
    client: AsyncClient,
) -> None:
    await enroll_admin(client)
    account = await _create_account(client)
    contact = await _create_contact(
        client,
        fullName="Carla Gomez",
        primaryEmail="carla@example.com",
        accountId=account["id"],
    )
    assert contact["accountId"] == account["id"]
    assert contact["primaryEmail"] == "carla@example.com"
    assert "contact.created" in await _audit_types(client)


async def test_tc_b_6_contact_search_matches_only(client: AsyncClient) -> None:
    await enroll_admin(client)
    maria = await _create_contact(client, fullName="Maria Lopez")
    await _create_contact(client, fullName="Juan Perez")
    hit = await client.get("/api/v1/contacts", params={"q": "maria"})
    assert hit.status_code == 200
    hit_ids = [item["id"] for item in hit.json()["items"]]
    assert maria["id"] in hit_ids
    assert len(hit_ids) == 1
    miss = await client.get("/api/v1/contacts", params={"q": "zzzznomatch"})
    assert miss.status_code == 200
    assert miss.json()["items"] == []


async def test_tc_b_7_contacts_filter_by_account(client: AsyncClient) -> None:
    await enroll_admin(client)
    account_a = await _create_account(client, name="Cuenta A")
    account_b = await _create_account(client, name="Cuenta B")
    in_a = await _create_contact(client, fullName="Alpha", accountId=account_a["id"])
    in_b = await _create_contact(client, fullName="Bravo", accountId=account_b["id"])
    listed = await client.get(
        "/api/v1/contacts", params={"accountId": account_a["id"]}
    )
    assert listed.status_code == 200
    ids = [item["id"] for item in listed.json()["items"]]
    assert in_a["id"] in ids
    assert in_b["id"] not in ids


async def test_tc_b_8_archive_contact_hides_and_audits(client: AsyncClient) -> None:
    await enroll_admin(client)
    contact = await _create_contact(client)
    archived = await client.post(
        f"/api/v1/contacts/{contact['id']}/archive", headers=CSRF_HEADERS
    )
    assert archived.status_code == 200
    listed = await client.get("/api/v1/contacts")
    assert contact["id"] not in [item["id"] for item in listed.json()["items"]]
    fetched = await client.get(f"/api/v1/contacts/{contact['id']}")
    assert fetched.status_code == 404
    assert "contact.archived" in await _audit_types(client)


async def test_tc_b_9_patch_contact_reflects_and_audits(client: AsyncClient) -> None:
    await enroll_admin(client)
    contact = await _create_contact(client)
    patched = await client.patch(
        f"/api/v1/contacts/{contact['id']}",
        headers=CSRF_HEADERS,
        json={
            "jobTitle": "Gerente",
            "notes": "VIP",
            "emails": ["maria@example.com", "m.lopez@example.com"],
        },
    )
    assert patched.status_code == 200
    body = patched.json()
    assert body["jobTitle"] == "Gerente"
    assert body["notes"] == "VIP"
    assert body["emails"] == ["maria@example.com", "m.lopez@example.com"]
    fetched = await client.get(f"/api/v1/contacts/{contact['id']}")
    assert fetched.json()["jobTitle"] == "Gerente"
    assert "contact.updated" in await _audit_types(client)


# ---- consent (RF-009) ---------------------------------------------------


async def test_tc_b_10_record_consent_granted_audits(client: AsyncClient) -> None:
    await enroll_admin(client)
    contact = await _create_contact(client)
    recorded = await client.post(
        f"/api/v1/contacts/{contact['id']}/consent",
        headers=CSRF_HEADERS,
        json={"status": "granted", "basis": "consentimiento"},
    )
    assert recorded.status_code == 200
    body = recorded.json()
    assert body["consentStatus"] == "granted"
    assert body["consentBasis"] == "consentimiento"
    assert body["consentRecordedAt"] is not None
    assert "contact.consent.recorded" in await _audit_types(client)


async def test_tc_b_11_consent_granted_without_basis_is_422(
    client: AsyncClient,
) -> None:
    await enroll_admin(client)
    contact = await _create_contact(client)
    rejected = await client.post(
        f"/api/v1/contacts/{contact['id']}/consent",
        headers=CSRF_HEADERS,
        json={"status": "granted"},
    )
    assert rejected.status_code == 422
    assert rejected.json()["code"] == "validation_error"
    fetched = await client.get(f"/api/v1/contacts/{contact['id']}")
    assert fetched.json()["consentStatus"] == "unknown"
    assert fetched.json()["consentRecordedAt"] is None


# ---- assignment ---------------------------------------------------------


async def test_tc_b_12_assignment_sets_and_clears_owner(client: AsyncClient) -> None:
    admin = await enroll_admin(client)
    owner_id = str(admin["me"]["userId"])
    contact = await _create_contact(client)
    assigned = await client.post(
        f"/api/v1/contacts/{contact['id']}/assignment",
        headers=CSRF_HEADERS,
        json={"ownerUserId": owner_id},
    )
    assert assigned.status_code == 200
    assert assigned.json()["ownerUserId"] == owner_id
    assert "contact.assigned" in await _audit_types(client)
    cleared = await client.post(
        f"/api/v1/contacts/{contact['id']}/assignment",
        headers=CSRF_HEADERS,
        json={"ownerUserId": None},
    )
    assert cleared.status_code == 200
    assert cleared.json()["ownerUserId"] is None


# ---- RBAC + isolation ---------------------------------------------------


async def test_tc_b_13_vendedor_can_read_and_write_contacts(
    client: AsyncClient,
) -> None:
    admin = await enroll_admin(client)
    vendedor = await _enroll_vendedor(client, str(admin["me"]["tenantId"]))
    try:
        created = await vendedor.post(
            "/api/v1/contacts",
            headers=CSRF_HEADERS,
            json={"fullName": "Contacto del Vendedor"},
        )
        assert created.status_code == 201, created.text
        listed = await vendedor.get("/api/v1/contacts")
        assert listed.status_code == 200
        ids = [item["id"] for item in listed.json()["items"]]
        assert created.json()["id"] in ids
    finally:
        await vendedor.aclose()


async def test_tc_b_14_non_full_scope_is_forbidden(client: AsyncClient) -> None:
    payload = signup_payload()
    await signup_and_verify(client, payload)
    login = await client.post(
        "/api/v1/public/sessions",
        headers=CSRF_HEADERS,
        json={"email": payload["email"], "password": VALID_PASSWORD},
    )
    assert login.status_code == 200
    assert login.json()["status"] == "mfa_enrollment_required"
    listed = await client.get("/api/v1/contacts")
    assert listed.status_code == 403
    assert listed.json()["code"] == "forbidden"


async def test_tc_b_15_cross_tenant_contact_is_not_found(client: AsyncClient) -> None:
    await enroll_admin(client)
    contact = await _create_contact(client, fullName="Titular Tenant A")
    async with await _new_client() as other:
        await enroll_admin(other)
        fetched = await other.get(f"/api/v1/contacts/{contact['id']}")
        assert fetched.status_code == 404
        assert fetched.json()["code"] == "not_found"
        missing = await other.get(f"/api/v1/contacts/{uuid4()}")
        assert missing.status_code == 404
