from urllib.parse import parse_qs, urlparse
from uuid import uuid4

import pyotp
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from app.db.engine import engine
from app.main import app
from tests.conftest import CSRF_HEADERS, VALID_PASSWORD, signup_payload, unique_email

_INVITE_PASSWORD = "InvitePass1x"


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


async def _invite_count(tenant_id: str) -> int:
    async with engine.connect() as conn:
        count = await conn.scalar(
            text(
                """
                SELECT count(*) FROM catalog.invites
                WHERE tenant_id = :tenant_id
                  AND accepted_at IS NULL
                  AND expires_at > now()
                """
            ),
            {"tenant_id": tenant_id},
        )
    return int(count or 0)


async def _user_row(user_id: str) -> dict:
    async with engine.connect() as conn:
        row = (
            await conn.execute(
                text(
                    """
                    SELECT id, role, status, mfa_status, deactivated_at
                    FROM catalog.users
                    WHERE id = :id
                    """
                ),
                {"id": user_id},
            )
        ).mappings().first()
    assert row is not None
    return dict(row)


async def _set_seat_cap(tenant_id: str, seat_cap: int) -> None:
    async with engine.begin() as conn:
        await conn.execute(
            text("UPDATE catalog.tenants SET seat_cap = :cap WHERE id = :id"),
            {"cap": seat_cap, "id": tenant_id},
        )


async def _new_client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def test_tc_5_4_gerente_cannot_invite(client: AsyncClient) -> None:
    admin = await _enroll_admin(client)
    tenant_id = str(admin["me"]["tenantId"])
    await _set_seat_cap(tenant_id, 3)
    gerente_email = unique_email()
    created = await client.post(
        "/api/v1/invites",
        headers=CSRF_HEADERS,
        json={
            "email": gerente_email,
            "role": "gerente",
            "fullName": "Gabriela Gerente",
        },
    )
    assert created.status_code == 201
    token = await _outbox_token(gerente_email, "invite")
    async with await _new_client() as gerente:
        accepted = await gerente.post(
            "/api/v1/public/invites/accept",
            headers=CSRF_HEADERS,
            json={"token": token, "password": _INVITE_PASSWORD},
        )
        assert accepted.status_code == 200
        before = await _invite_count(tenant_id)
        forbidden = await gerente.post(
            "/api/v1/invites",
            headers=CSRF_HEADERS,
            json={
                "email": unique_email(),
                "role": "vendedor",
                "fullName": "No Debe Entrar",
            },
        )
        assert forbidden.status_code == 403
        assert forbidden.headers["content-type"].startswith("application/problem+json")
        assert await _invite_count(tenant_id) == before


async def test_tc_5_3_third_invite_exceeds_seat_cap(client: AsyncClient) -> None:
    admin = await _enroll_admin(client)
    first = await client.post(
        "/api/v1/invites",
        headers=CSRF_HEADERS,
        json={
            "email": unique_email(),
            "role": "vendedor",
            "fullName": "Primera Invitada",
        },
    )
    assert first.status_code == 201
    second = await client.post(
        "/api/v1/invites",
        headers=CSRF_HEADERS,
        json={
            "email": unique_email(),
            "role": "vendedor",
            "fullName": "Tercera Persona",
        },
    )
    assert second.status_code == 409
    body = second.json()
    assert body["code"] == "seat_cap_exceeded"
    assert second.headers["content-type"].startswith("application/problem+json")
    assert await _invite_count(str(admin["me"]["tenantId"])) == 1


async def test_tc_5_6_existing_email_invite_is_email_taken(
    client: AsyncClient,
) -> None:
    admin = await _enroll_admin(client)
    response = await client.post(
        "/api/v1/invites",
        headers=CSRF_HEADERS,
        json={
            "email": str(admin["signup"]["email"]),
            "role": "vendedor",
            "fullName": "Duplicado",
        },
    )
    assert response.status_code == 409
    assert response.json()["code"] == "email_taken"
    assert response.headers["content-type"].startswith("application/problem+json")
    assert await _invite_count(str(admin["me"]["tenantId"])) == 0


async def test_tc_6_3_last_admin_cannot_be_deactivated(client: AsyncClient) -> None:
    admin = await _enroll_admin(client)
    user_id = str(admin["me"]["userId"])
    response = await client.post(
        f"/api/v1/users/{user_id}/deactivation",
        headers=CSRF_HEADERS,
    )
    assert response.status_code == 409
    assert response.json()["code"] == "last_admin"
    row = await _user_row(user_id)
    assert row["status"] == "active"
    assert row["deactivated_at"] is None


async def test_tc_6_2_deactivate_frees_a_seat(client: AsyncClient) -> None:
    await _enroll_admin(client)
    teammate_email = unique_email()
    invited = await client.post(
        "/api/v1/invites",
        headers=CSRF_HEADERS,
        json={
            "email": teammate_email,
            "role": "vendedor",
            "fullName": "Vendedor Uno",
        },
    )
    assert invited.status_code == 201
    token = await _outbox_token(teammate_email, "invite")
    async with await _new_client() as teammate:
        accepted = await teammate.post(
            "/api/v1/public/invites/accept",
            headers=CSRF_HEADERS,
            json={"token": token, "password": _INVITE_PASSWORD},
        )
        assert accepted.status_code == 200
        user_id = accepted.json()["userId"]
    blocked = await client.post(
        "/api/v1/invites",
        headers=CSRF_HEADERS,
        json={
            "email": unique_email(),
            "role": "vendedor",
            "fullName": "Sin Cupo",
        },
    )
    assert blocked.status_code == 409
    assert blocked.json()["code"] == "seat_cap_exceeded"
    deactivated = await client.post(
        f"/api/v1/users/{user_id}/deactivation",
        headers=CSRF_HEADERS,
    )
    assert deactivated.status_code == 200
    body = deactivated.json()
    assert body["status"] == "deactivated"
    assert body["id"] == user_id
    row = await _user_row(user_id)
    assert row["status"] == "deactivated"
    assert row["deactivated_at"] is not None
    freed = await client.post(
        "/api/v1/invites",
        headers=CSRF_HEADERS,
        json={
            "email": unique_email(),
            "role": "vendedor",
            "fullName": "Nuevo Cupo",
        },
    )
    assert freed.status_code == 201


async def test_tc_6_5_promote_vendedor_to_gerente_sets_mfa_and_revokes(
    client: AsyncClient,
) -> None:
    await _enroll_admin(client)
    vendedor_email = unique_email()
    invited = await client.post(
        "/api/v1/invites",
        headers=CSRF_HEADERS,
        json={
            "email": vendedor_email,
            "role": "vendedor",
            "fullName": "Vendedor Dos",
        },
    )
    assert invited.status_code == 201
    token = await _outbox_token(vendedor_email, "invite")
    async with await _new_client() as vendedor:
        accepted = await vendedor.post(
            "/api/v1/public/invites/accept",
            headers=CSRF_HEADERS,
            json={"token": token, "password": _INVITE_PASSWORD},
        )
        assert accepted.status_code == 200
        principal = accepted.json()
        assert principal["role"] == "vendedor"
        assert "nexus_session" in accepted.cookies
        me_before = await vendedor.get("/api/v1/me")
        assert me_before.status_code == 200
        user_id = principal["userId"]
        changed = await client.patch(
            f"/api/v1/users/{user_id}/role",
            headers=CSRF_HEADERS,
            json={"role": "gerente"},
        )
        assert changed.status_code == 200
        body = changed.json()
        assert body["role"] == "gerente"
        assert body["mfaStatus"] == "pending"
        row = await _user_row(user_id)
        assert row["role"] == "gerente"
        assert row["mfa_status"] == "pending"
        me_after = await vendedor.get("/api/v1/me")
        assert me_after.status_code == 401


async def test_tc_5_1_admin_invite_creates_pending_hashed_token(
    client: AsyncClient,
) -> None:
    admin = await _enroll_admin(client)
    email = unique_email()
    response = await client.post(
        "/api/v1/invites",
        headers=CSRF_HEADERS,
        json={"email": email, "role": "vendedor", "fullName": "Invitado"},
    )
    assert response.status_code == 201
    async with engine.connect() as conn:
        invite = (
            await conn.execute(
                text(
                    """
                    SELECT token_hash, role, full_name, expires_at, accepted_at
                    FROM catalog.invites
                    WHERE lower(email) = lower(:email)
                    """
                ),
                {"email": email},
            )
        ).mappings().first()
        hours = await conn.scalar(
            text(
                """
                SELECT extract(epoch from (expires_at - created_at)) / 3600.0
                FROM catalog.invites
                WHERE lower(email) = lower(:email)
                """
            ),
            {"email": email},
        )
    assert invite is not None
    assert invite["role"] == "vendedor"
    assert invite["full_name"] == "Invitado"
    assert invite["accepted_at"] is None
    assert len(str(invite["token_hash"])) == 64
    raw = await _outbox_token(email, "invite")
    assert raw not in str(invite["token_hash"])
    assert abs(float(hours) - 72.0) < 0.1
    assert await _invite_count(str(admin["me"]["tenantId"])) == 1


async def test_tc_6_4_last_admin_cannot_be_demoted(client: AsyncClient) -> None:
    admin = await _enroll_admin(client)
    user_id = str(admin["me"]["userId"])
    response = await client.patch(
        f"/api/v1/users/{user_id}/role",
        headers=CSRF_HEADERS,
        json={"role": "gerente"},
    )
    assert response.status_code == 409
    assert response.json()["code"] == "last_admin"
    row = await _user_row(user_id)
    assert row["role"] == "administrador"


async def test_tc_6_1_admin_lists_users_and_reads_tenant(
    client: AsyncClient,
) -> None:
    admin = await _enroll_admin(client)
    users = await client.get("/api/v1/users")
    assert users.status_code == 200
    listed = users.json()
    assert any(item["id"] == admin["me"]["userId"] for item in listed)
    tenant = await client.get("/api/v1/tenant")
    assert tenant.status_code == 200
    body = tenant.json()
    assert body["seatCap"] == 2
    assert body["id"] == admin["me"]["tenantId"]
    patched = await client.patch(
        "/api/v1/tenant",
        headers=CSRF_HEADERS,
        json={"companyName": "Acme Actualizada"},
    )
    assert patched.status_code == 200
    assert patched.json()["companyName"] == "Acme Actualizada"


async def test_invite_without_csrf_is_rejected(client: AsyncClient) -> None:
    await _enroll_admin(client)
    response = await client.post(
        "/api/v1/invites",
        json={
            "email": unique_email(),
            "role": "vendedor",
            "fullName": "Sin CSRF",
        },
    )
    assert response.status_code == 403
    assert response.json()["code"] == "csrf_rejected"


async def test_unknown_user_deactivation_is_not_found(client: AsyncClient) -> None:
    await _enroll_admin(client)
    response = await client.post(
        f"/api/v1/users/{uuid4()}/deactivation",
        headers=CSRF_HEADERS,
    )
    assert response.status_code == 404
    assert response.json()["code"] == "not_found"


async def test_tc_5_2_second_seat_fills_starter_cap(client: AsyncClient) -> None:
    admin = await _enroll_admin(client)
    created = await client.post(
        "/api/v1/invites",
        headers=CSRF_HEADERS,
        json={
            "email": unique_email(),
            "role": "vendedor",
            "fullName": "Segundo Asiento",
        },
    )
    assert created.status_code == 201
    tenant_id = str(admin["me"]["tenantId"])
    async with engine.connect() as conn:
        active = await conn.scalar(
            text(
                """
                SELECT count(*) FROM catalog.users
                WHERE tenant_id = :tenant_id AND status = 'active'
                """
            ),
            {"tenant_id": tenant_id},
        )
        pending = await conn.scalar(
            text(
                """
                SELECT count(*) FROM catalog.invites
                WHERE tenant_id = :tenant_id
                  AND accepted_at IS NULL
                  AND expires_at > now()
                """
            ),
            {"tenant_id": tenant_id},
        )
    assert int(active or 0) + int(pending or 0) == 2


async def test_tc_5_5_vendedor_cannot_invite(client: AsyncClient) -> None:
    admin = await _enroll_admin(client)
    await _set_seat_cap(str(admin["me"]["tenantId"]), 3)
    vendedor_email = unique_email()
    created = await client.post(
        "/api/v1/invites",
        headers=CSRF_HEADERS,
        json={
            "email": vendedor_email,
            "role": "vendedor",
            "fullName": "Vendedor Invite",
        },
    )
    assert created.status_code == 201
    token = await _outbox_token(vendedor_email, "invite")
    async with await _new_client() as vendedor:
        accepted = await vendedor.post(
            "/api/v1/public/invites/accept",
            headers=CSRF_HEADERS,
            json={"token": token, "password": _INVITE_PASSWORD},
        )
        assert accepted.status_code == 200
        before = await _invite_count(str(admin["me"]["tenantId"]))
        forbidden = await vendedor.post(
            "/api/v1/invites",
            headers=CSRF_HEADERS,
            json={
                "email": unique_email(),
                "role": "vendedor",
                "fullName": "No Debe Entrar",
            },
        )
        assert forbidden.status_code == 403
        assert forbidden.headers["content-type"].startswith("application/problem+json")
        assert await _invite_count(str(admin["me"]["tenantId"])) == before


async def test_tc_5_7_invite_token_is_single_use_and_expires(
    client: AsyncClient,
) -> None:
    admin = await _enroll_admin(client)
    await _set_seat_cap(str(admin["me"]["tenantId"]), 4)
    email = unique_email()
    created = await client.post(
        "/api/v1/invites",
        headers=CSRF_HEADERS,
        json={"email": email, "role": "vendedor", "fullName": "Un Solo Uso"},
    )
    assert created.status_code == 201
    token = await _outbox_token(email, "invite")
    async with await _new_client() as invitee:
        first = await invitee.post(
            "/api/v1/public/invites/accept",
            headers=CSRF_HEADERS,
            json={"token": token, "password": _INVITE_PASSWORD},
        )
        assert first.status_code == 200
        assert first.json().get("userId")
        reused = await invitee.post(
            "/api/v1/public/invites/accept",
            headers=CSRF_HEADERS,
            json={"token": token, "password": _INVITE_PASSWORD},
        )
        assert reused.status_code == 400
        assert reused.json()["code"] == "invalid_token"

    expired_email = unique_email()
    pending = await client.post(
        "/api/v1/invites",
        headers=CSRF_HEADERS,
        json={
            "email": expired_email,
            "role": "vendedor",
            "fullName": "Expirada",
        },
    )
    assert pending.status_code == 201
    expired_token = await _outbox_token(expired_email, "invite")
    async with engine.begin() as conn:
        await conn.execute(
            text(
                """
                UPDATE catalog.invites
                SET expires_at = now() - interval '1 hour'
                WHERE lower(email) = lower(:email)
                """
            ),
            {"email": expired_email},
        )
    expired = await client.post(
        "/api/v1/public/invites/accept",
        headers=CSRF_HEADERS,
        json={"token": expired_token, "password": _INVITE_PASSWORD},
    )
    assert expired.status_code == 400
    assert expired.json()["code"] == "invalid_token"


async def test_tc_5_8_concurrent_invites_cannot_oversell_last_seat(
    client: AsyncClient,
) -> None:
    import asyncio

    admin = await _enroll_admin(client)
    tenant_id = str(admin["me"]["tenantId"])
    cookies = dict(client.cookies)

    async def _invite(email: str):
        async with await _new_client() as other:
            for key, value in cookies.items():
                other.cookies.set(key, value)
            return await other.post(
                "/api/v1/invites",
                headers=CSRF_HEADERS,
                json={
                    "email": email,
                    "role": "vendedor",
                    "fullName": "Carrera De Cupo",
                },
            )

    first, second = await asyncio.gather(
        _invite(unique_email()), _invite(unique_email())
    )
    statuses = sorted([first.status_code, second.status_code])
    assert statuses == [201, 409]
    loser = first if first.status_code == 409 else second
    assert loser.json()["code"] == "seat_cap_exceeded"
    assert await _invite_count(tenant_id) == 1


async def test_tc_6_6_gerente_and_vendedor_cannot_use_admin_surfaces(
    client: AsyncClient,
) -> None:
    admin = await _enroll_admin(client)
    await _set_seat_cap(str(admin["me"]["tenantId"]), 4)
    gerente_email = unique_email()
    vendedor_email = unique_email()
    for email, role, name in (
        (gerente_email, "gerente", "Gabriela"),
        (vendedor_email, "vendedor", "Victor"),
    ):
        created = await client.post(
            "/api/v1/invites",
            headers=CSRF_HEADERS,
            json={"email": email, "role": role, "fullName": name},
        )
        assert created.status_code == 201

    gerente_token = await _outbox_token(gerente_email, "invite")
    vendedor_token = await _outbox_token(vendedor_email, "invite")

    async with await _new_client() as gerente:
        accepted = await gerente.post(
            "/api/v1/public/invites/accept",
            headers=CSRF_HEADERS,
            json={"token": gerente_token, "password": _INVITE_PASSWORD},
        )
        assert accepted.status_code == 200
        start = await gerente.post("/api/v1/me/mfa/totp", headers=CSRF_HEADERS)
        secret = parse_qs(urlparse(start.json()["otpauthUrl"]).query)["secret"][0]
        confirm = await gerente.post(
            "/api/v1/me/mfa/totp/confirm",
            headers=CSRF_HEADERS,
            json={"code": pyotp.TOTP(secret).now(), "backupCodesSaved": True},
        )
        assert confirm.status_code == 200
        me = await gerente.get("/api/v1/me")
        assert me.status_code == 200
        assert me.json()["scope"] == "full"
        await _assert_admin_forbidden(gerente)

    async with await _new_client() as vendedor:
        accepted = await vendedor.post(
            "/api/v1/public/invites/accept",
            headers=CSRF_HEADERS,
            json={"token": vendedor_token, "password": _INVITE_PASSWORD},
        )
        assert accepted.status_code == 200
        me = await vendedor.get("/api/v1/me")
        assert me.status_code == 200
        await _assert_admin_forbidden(vendedor)


async def test_tc_6_7_users_are_deactivated_not_deleted(client: AsyncClient) -> None:
    await _enroll_admin(client)
    email = unique_email()
    invited = await client.post(
        "/api/v1/invites",
        headers=CSRF_HEADERS,
        json={"email": email, "role": "vendedor", "fullName": "Para Desactivar"},
    )
    assert invited.status_code == 201
    token = await _outbox_token(email, "invite")
    async with await _new_client() as teammate:
        accepted = await teammate.post(
            "/api/v1/public/invites/accept",
            headers=CSRF_HEADERS,
            json={"token": token, "password": _INVITE_PASSWORD},
        )
        user_id = accepted.json()["userId"]
    deleted = await client.delete(f"/api/v1/users/{user_id}", headers=CSRF_HEADERS)
    assert deleted.status_code in {404, 405}
    deactivated = await client.post(
        f"/api/v1/users/{user_id}/deactivation",
        headers=CSRF_HEADERS,
    )
    assert deactivated.status_code == 200
    row = await _user_row(user_id)
    assert row["status"] == "deactivated"
    assert row["id"]


async def test_tc_6_8_role_or_deactivation_is_reread_every_request(
    client: AsyncClient,
) -> None:
    await _enroll_admin(client)
    email = unique_email()
    invited = await client.post(
        "/api/v1/invites",
        headers=CSRF_HEADERS,
        json={"email": email, "role": "vendedor", "fullName": "Sesion Abierta"},
    )
    assert invited.status_code == 201
    token = await _outbox_token(email, "invite")
    async with await _new_client() as teammate:
        accepted = await teammate.post(
            "/api/v1/public/invites/accept",
            headers=CSRF_HEADERS,
            json={"token": token, "password": _INVITE_PASSWORD},
        )
        assert accepted.status_code == 200
        user_id = accepted.json()["userId"]
        me_before = await teammate.get("/api/v1/me")
        assert me_before.status_code == 200
        deactivated = await client.post(
            f"/api/v1/users/{user_id}/deactivation",
            headers=CSRF_HEADERS,
        )
        assert deactivated.status_code == 200
        me_after = await teammate.get("/api/v1/me")
        assert me_after.status_code == 401


async def _assert_admin_forbidden(actor: AsyncClient) -> None:
    listed = await actor.get("/api/v1/users")
    assert listed.status_code == 403
    patched = await actor.patch(
        "/api/v1/tenant",
        headers=CSRF_HEADERS,
        json={"companyName": "Hack"},
    )
    assert patched.status_code == 403
    invited = await actor.post(
        "/api/v1/invites",
        headers=CSRF_HEADERS,
        json={
            "email": unique_email(),
            "role": "vendedor",
            "fullName": "No",
        },
    )
    assert invited.status_code == 403
    inbox = await actor.get("/api/v1/arco-requests")
    assert inbox.status_code == 403
    audit = await actor.get("/api/v1/audit-events")
    assert audit.status_code == 403
