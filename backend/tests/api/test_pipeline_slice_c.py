from urllib.parse import parse_qs, urlparse
from uuid import uuid4

import pyotp
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from app.db.engine import engine
from app.main import app
from tests.conftest import (
    CSRF_HEADERS,
    enroll_admin,
    signup_and_verify,
    signup_payload,
    unique_email,
    VALID_PASSWORD,
)
from tests.conftest import outbox_token as _outbox_token

_MEMBER_PASSWORD = "MemberPass1x"


async def _new_client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def _set_seat_cap(tenant_id: str, seat_cap: int) -> None:
    async with engine.begin() as conn:
        await conn.execute(
            text("UPDATE catalog.tenants SET seat_cap = :cap WHERE id = :id"),
            {"cap": seat_cap, "id": tenant_id},
        )


async def _tenant_schema(tenant_id: str) -> str:
    async with engine.connect() as conn:
        schema = await conn.scalar(
            text("SELECT schema_name FROM catalog.tenants WHERE id = :id"),
            {"id": tenant_id},
        )
    assert schema is not None
    return str(schema)


async def _enroll_mfa(member: AsyncClient) -> None:
    start = await member.post("/api/v1/me/mfa/totp", headers=CSRF_HEADERS)
    assert start.status_code == 200, start.text
    secret = parse_qs(urlparse(start.json()["otpauthUrl"]).query)["secret"][0]
    confirm = await member.post(
        "/api/v1/me/mfa/totp/confirm",
        headers=CSRF_HEADERS,
        json={"code": pyotp.TOTP(secret).now(), "backupCodesSaved": True},
    )
    assert confirm.status_code == 200, confirm.text


async def _enroll_member(admin: AsyncClient, tenant_id: str, role: str) -> AsyncClient:
    await _set_seat_cap(tenant_id, 5)
    email = unique_email()
    invited = await admin.post(
        "/api/v1/invites",
        headers=CSRF_HEADERS,
        json={"email": email, "role": role, "fullName": f"Miembro {role}"},
    )
    assert invited.status_code == 201, invited.text
    token = await _outbox_token(email, "invite")
    member = await _new_client()
    accepted = await member.post(
        "/api/v1/public/invites/accept",
        headers=CSRF_HEADERS,
        json={"token": token, "password": _MEMBER_PASSWORD},
    )
    assert accepted.status_code == 200, accepted.text
    if role in ("administrador", "gerente"):
        await _enroll_mfa(member)
    return member


async def _audit_types(admin: AsyncClient) -> set[str]:
    listed = await admin.get("/api/v1/audit-events")
    assert listed.status_code == 200, listed.text
    return {item["eventType"] for item in listed.json()["items"]}


async def _default_pipeline(client: AsyncClient) -> dict:
    listed = await client.get("/api/v1/pipelines")
    assert listed.status_code == 200, listed.text
    items = listed.json()["items"]
    for pipeline in items:
        if pipeline["isDefault"]:
            return pipeline
    return items[0]


def _stage(pipeline: dict, name: str) -> dict:
    for stage in pipeline["stages"]:
        if stage["name"] == name:
            return stage
    raise AssertionError(f"stage {name} not found")


async def _create_deal(client: AsyncClient, **body: object) -> dict:
    payload: dict[str, object] = {"name": "Negocio"}
    payload.update(body)
    created = await client.post("/api/v1/deals", headers=CSRF_HEADERS, json=payload)
    assert created.status_code == 201, created.text
    return created.json()


# ---- pipelines & stages (RF-010, RF-011) --------------------------------


async def test_tc_c_1_default_pipeline_seeded(client: AsyncClient) -> None:
    await enroll_admin(client)
    pipeline = await _default_pipeline(client)
    assert pipeline["name"] == "Ventas"
    assert pipeline["isDefault"] is True
    names = [stage["name"] for stage in pipeline["stages"]]
    assert names == ["Prospecto", "Calificado", "Propuesta", "Negociación", "Cierre"]
    positions = [stage["position"] for stage in pipeline["stages"]]
    assert positions == [1, 2, 3, 4, 5]


async def test_tc_c_2_create_pipeline_flips_default(client: AsyncClient) -> None:
    await enroll_admin(client)
    ventas = await _default_pipeline(client)
    created = await client.post(
        "/api/v1/pipelines",
        headers=CSRF_HEADERS,
        json={"name": "Enterprise", "isDefault": True},
    )
    assert created.status_code == 201, created.text
    assert created.json()["isDefault"] is True
    listed = (await client.get("/api/v1/pipelines")).json()["items"]
    by_id = {p["id"]: p for p in listed}
    assert by_id[created.json()["id"]]["isDefault"] is True
    assert by_id[ventas["id"]]["isDefault"] is False
    defaults = [p for p in listed if p["isDefault"]]
    assert len(defaults) == 1
    assert "pipeline.created" in await _audit_types(client)


async def test_tc_c_3_stage_create_update_reorder(client: AsyncClient) -> None:
    await enroll_admin(client)
    pipeline = await _default_pipeline(client)
    pid = pipeline["id"]
    added = await client.post(
        f"/api/v1/pipelines/{pid}/stages",
        headers=CSRF_HEADERS,
        json={"name": "Demo", "probability": 50, "rottingDays": 5},
    )
    assert added.status_code == 201, added.text
    stage = added.json()
    assert stage["position"] == 6
    patched = await client.patch(
        f"/api/v1/stages/{stage['id']}",
        headers=CSRF_HEADERS,
        json={"name": "Demostración", "probability": 55},
    )
    assert patched.status_code == 200
    assert patched.json()["name"] == "Demostración"
    assert patched.json()["probability"] == 55
    refreshed = await _default_pipeline(client)
    ids = [s["id"] for s in refreshed["stages"]]
    reordered_ids = list(reversed(ids))
    reordered = await client.post(
        f"/api/v1/pipelines/{pid}/stages/reorder",
        headers=CSRF_HEADERS,
        json={"stageIds": reordered_ids},
    )
    assert reordered.status_code == 200, reordered.text
    new_order = [s["id"] for s in reordered.json()["stages"]]
    assert new_order == reordered_ids
    audit = await _audit_types(client)
    assert {"stage.created", "stage.updated", "stage.reordered"} <= audit


async def test_tc_c_4_delete_stage_guarded(client: AsyncClient) -> None:
    await enroll_admin(client)
    pipeline = await _default_pipeline(client)
    pid = pipeline["id"]
    prospecto = _stage(pipeline, "Prospecto")
    await _create_deal(client, pipelineId=pid, stageId=prospecto["id"])
    blocked = await client.delete(
        f"/api/v1/stages/{prospecto['id']}", headers=CSRF_HEADERS
    )
    assert blocked.status_code == 422
    assert blocked.json()["code"] == "validation_error"
    added = await client.post(
        f"/api/v1/pipelines/{pid}/stages",
        headers=CSRF_HEADERS,
        json={"name": "Temporal"},
    )
    temp_id = added.json()["id"]
    removed = await client.delete(
        f"/api/v1/stages/{temp_id}", headers=CSRF_HEADERS
    )
    assert removed.status_code == 204
    assert "stage.deleted" in await _audit_types(client)


async def test_tc_c_5_archive_default_pipeline_is_422(client: AsyncClient) -> None:
    await enroll_admin(client)
    pipeline = await _default_pipeline(client)
    blocked = await client.post(
        f"/api/v1/pipelines/{pipeline['id']}/archive", headers=CSRF_HEADERS
    )
    assert blocked.status_code == 422
    assert blocked.json()["code"] == "validation_error"


# ---- deals (RF-012) -----------------------------------------------------


async def test_tc_c_6_create_deal_defaults_first_stage(client: AsyncClient) -> None:
    await enroll_admin(client)
    pipeline = await _default_pipeline(client)
    prospecto = _stage(pipeline, "Prospecto")
    deal = await _create_deal(client, name="Deal Uno", pipelineId=pipeline["id"])
    assert deal["stageId"] == prospecto["id"]
    assert deal["probability"] == prospecto["probability"]
    assert deal["status"] == "open"
    history = await client.get(f"/api/v1/deals/{deal['id']}/history")
    assert history.status_code == 200
    events = history.json()["items"]
    assert len(events) == 1
    assert events[0]["fromStageId"] is None
    assert events[0]["toStageId"] == prospecto["id"]
    assert "deal.created" in await _audit_types(client)


async def test_tc_c_7_deal_filters(client: AsyncClient) -> None:
    await enroll_admin(client)
    pipeline = await _default_pipeline(client)
    pid = pipeline["id"]
    prospecto = _stage(pipeline, "Prospecto")
    calificado = _stage(pipeline, "Calificado")
    alpha = await _create_deal(client, name="Alpha Contrato", pipelineId=pid)
    await _create_deal(
        client, name="Beta Negocio", pipelineId=pid, stageId=calificado["id"]
    )
    by_q = await client.get("/api/v1/deals", params={"q": "alpha"})
    ids = [d["id"] for d in by_q.json()["items"]]
    assert alpha["id"] in ids and len(ids) == 1
    by_stage = await client.get("/api/v1/deals", params={"stageId": calificado["id"]})
    stage_ids = {d["stageId"] for d in by_stage.json()["items"]}
    assert stage_ids == {calificado["id"]}
    await client.post(
        f"/api/v1/deals/{alpha['id']}/status",
        headers=CSRF_HEADERS,
        json={"status": "won"},
    )
    by_status = await client.get("/api/v1/deals", params={"status": "won"})
    won_ids = [d["id"] for d in by_status.json()["items"]]
    assert alpha["id"] in won_ids
    assert all(d["status"] == "won" for d in by_status.json()["items"])
    assert prospecto["id"]  # sanity


async def test_tc_c_8_patch_deal_reflects_and_audits(client: AsyncClient) -> None:
    await enroll_admin(client)
    pipeline = await _default_pipeline(client)
    deal = await _create_deal(client, pipelineId=pipeline["id"])
    patched = await client.patch(
        f"/api/v1/deals/{deal['id']}",
        headers=CSRF_HEADERS,
        json={"value": "2500000.50", "closeDate": "2026-12-01"},
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["value"] == "2500000.50"
    assert patched.json()["closeDate"] == "2026-12-01"
    fetched = await client.get(f"/api/v1/deals/{deal['id']}")
    assert fetched.json()["value"] == "2500000.50"
    assert "deal.updated" in await _audit_types(client)


async def test_tc_c_9_archive_deal_hides_and_404(client: AsyncClient) -> None:
    await enroll_admin(client)
    pipeline = await _default_pipeline(client)
    pid = pipeline["id"]
    deal = await _create_deal(client, pipelineId=pid)
    archived = await client.post(
        f"/api/v1/deals/{deal['id']}/archive", headers=CSRF_HEADERS
    )
    assert archived.status_code == 200
    listed = await client.get("/api/v1/deals")
    assert deal["id"] not in [d["id"] for d in listed.json()["items"]]
    board = await client.get(f"/api/v1/pipelines/{pid}/board")
    board_ids = [
        d["id"] for col in board.json()["stages"] for d in col["deals"]
    ]
    assert deal["id"] not in board_ids
    fetched = await client.get(f"/api/v1/deals/{deal['id']}")
    assert fetched.status_code == 404
    assert "deal.archived" in await _audit_types(client)


# ---- stage moves & history (RF-013) -------------------------------------


async def test_tc_c_10_move_records_history(client: AsyncClient) -> None:
    await enroll_admin(client)
    pipeline = await _default_pipeline(client)
    prospecto = _stage(pipeline, "Prospecto")
    propuesta = _stage(pipeline, "Propuesta")
    deal = await _create_deal(client, pipelineId=pipeline["id"])
    moved = await client.post(
        f"/api/v1/deals/{deal['id']}/stage",
        headers=CSRF_HEADERS,
        json={"toStageId": propuesta["id"], "reason": "Cliente pidió propuesta"},
    )
    assert moved.status_code == 200, moved.text
    assert moved.json()["stageId"] == propuesta["id"]
    assert moved.json()["probability"] == propuesta["probability"]
    history = (await client.get(f"/api/v1/deals/{deal['id']}/history")).json()["items"]
    assert history[0]["fromStageId"] == prospecto["id"]
    assert history[0]["toStageId"] == propuesta["id"]
    assert history[0]["reason"] == "Cliente pidió propuesta"
    assert "deal.stage_changed" in await _audit_types(client)


async def test_tc_c_11_move_to_foreign_pipeline_is_422(client: AsyncClient) -> None:
    await enroll_admin(client)
    pipeline_a = await _default_pipeline(client)
    deal = await _create_deal(client, pipelineId=pipeline_a["id"])
    created_b = await client.post(
        "/api/v1/pipelines", headers=CSRF_HEADERS, json={"name": "Pipeline B"}
    )
    pid_b = created_b.json()["id"]
    stage_b = await client.post(
        f"/api/v1/pipelines/{pid_b}/stages",
        headers=CSRF_HEADERS,
        json={"name": "Etapa B"},
    )
    blocked = await client.post(
        f"/api/v1/deals/{deal['id']}/stage",
        headers=CSRF_HEADERS,
        json={"toStageId": stage_b.json()["id"]},
    )
    assert blocked.status_code == 422
    assert blocked.json()["code"] == "validation_error"
    fetched = await client.get(f"/api/v1/deals/{deal['id']}")
    assert fetched.json()["stageId"] == deal["stageId"]


async def test_tc_c_12_status_lost_then_open(client: AsyncClient) -> None:
    await enroll_admin(client)
    pipeline = await _default_pipeline(client)
    deal = await _create_deal(client, pipelineId=pipeline["id"])
    lost = await client.post(
        f"/api/v1/deals/{deal['id']}/status",
        headers=CSRF_HEADERS,
        json={"status": "lost", "lostReason": "Precio alto"},
    )
    assert lost.status_code == 200
    assert lost.json()["status"] == "lost"
    assert lost.json()["lostReason"] == "Precio alto"
    reopened = await client.post(
        f"/api/v1/deals/{deal['id']}/status",
        headers=CSRF_HEADERS,
        json={"status": "open"},
    )
    assert reopened.json()["status"] == "open"
    assert reopened.json()["lostReason"] is None
    assert "deal.status_changed" in await _audit_types(client)


# ---- forecast & rotting (RF-015, RF-016) --------------------------------


async def test_tc_c_13_forecast_weighted_math(client: AsyncClient) -> None:
    await enroll_admin(client)
    pipeline = await _default_pipeline(client)
    pid = pipeline["id"]
    prospecto = _stage(pipeline, "Prospecto")
    propuesta = _stage(pipeline, "Propuesta")
    cierre = _stage(pipeline, "Cierre")
    await _create_deal(
        client,
        name="A",
        pipelineId=pid,
        stageId=prospecto["id"],
        value="1000000",
        probability=10,
        closeDate="2026-09-15",
    )
    await _create_deal(
        client,
        name="B",
        pipelineId=pid,
        stageId=propuesta["id"],
        value="2000000",
        probability=60,
        closeDate="2026-09-20",
    )
    await _create_deal(
        client,
        name="C",
        pipelineId=pid,
        stageId=cierre["id"],
        value="500000",
        probability=95,
    )
    lost = await _create_deal(
        client, name="D", pipelineId=pid, value="9000000", probability=10
    )
    await client.post(
        f"/api/v1/deals/{lost['id']}/status",
        headers=CSRF_HEADERS,
        json={"status": "lost", "lostReason": "x"},
    )
    forecast = await client.get(f"/api/v1/pipelines/{pid}/forecast")
    assert forecast.status_code == 200, forecast.text
    body = forecast.json()
    stages = {s["stageId"]: s for s in body["stages"]}
    assert stages[prospecto["id"]]["weighted"] == "100000.00"
    assert stages[propuesta["id"]]["weighted"] == "1200000.00"
    assert stages[cierre["id"]]["weighted"] == "475000.00"
    assert body["totals"]["count"] == 3
    assert body["totals"]["sum"] == "3500000.00"
    assert body["totals"]["weighted"] == "1775000.00"
    months = {m["month"]: m for m in body["months"]}
    assert months["2026-09"]["sum"] == "3000000.00"
    assert months["2026-09"]["weighted"] == "1300000.00"


async def test_tc_c_14_rotting_indicator(client: AsyncClient) -> None:
    admin = await enroll_admin(client)
    tenant_id = str(admin["me"]["tenantId"])
    pipeline = await _default_pipeline(client)
    fresh = await _create_deal(client, name="Fresco", pipelineId=pipeline["id"])
    stale = await _create_deal(client, name="Rancio", pipelineId=pipeline["id"])
    assert fresh["isRotting"] is False
    schema = await _tenant_schema(tenant_id)
    async with engine.begin() as conn:
        await conn.execute(
            text(
                f'UPDATE "{schema}".deals '
                "SET stage_changed_at = now() - interval '60 days' WHERE id = :id"
            ),
            {"id": stale["id"]},
        )
    refetched = await client.get(f"/api/v1/deals/{stale['id']}")
    assert refetched.json()["isRotting"] is True
    assert refetched.json()["daysInStage"] >= 60
    fresh_again = await client.get(f"/api/v1/deals/{fresh['id']}")
    assert fresh_again.json()["isRotting"] is False


# ---- RBAC + isolation ---------------------------------------------------


async def test_tc_c_15_vendedor_deals_but_no_manage(client: AsyncClient) -> None:
    admin = await enroll_admin(client)
    vendedor = await _enroll_member(client, str(admin["me"]["tenantId"]), "vendedor")
    try:
        pipeline = await _default_pipeline(vendedor)
        pid = pipeline["id"]
        propuesta = _stage(pipeline, "Propuesta")
        deal = await _create_deal(vendedor, pipelineId=pid)
        moved = await vendedor.post(
            f"/api/v1/deals/{deal['id']}/stage",
            headers=CSRF_HEADERS,
            json={"toStageId": propuesta["id"]},
        )
        assert moved.status_code == 200
        blocked_pipeline = await vendedor.post(
            "/api/v1/pipelines", headers=CSRF_HEADERS, json={"name": "Nope"}
        )
        assert blocked_pipeline.status_code == 403
        blocked_stage = await vendedor.post(
            f"/api/v1/pipelines/{pid}/stages",
            headers=CSRF_HEADERS,
            json={"name": "Nope"},
        )
        assert blocked_stage.status_code == 403
    finally:
        await vendedor.aclose()


async def test_tc_c_16_gerente_manages_stages(client: AsyncClient) -> None:
    admin = await enroll_admin(client)
    gerente = await _enroll_member(client, str(admin["me"]["tenantId"]), "gerente")
    try:
        pipeline = await _default_pipeline(gerente)
        pid = pipeline["id"]
        added = await gerente.post(
            f"/api/v1/pipelines/{pid}/stages",
            headers=CSRF_HEADERS,
            json={"name": "Etapa Gerente"},
        )
        assert added.status_code == 201, added.text
        refreshed = await _default_pipeline(gerente)
        ids = [s["id"] for s in refreshed["stages"]]
        reordered = await gerente.post(
            f"/api/v1/pipelines/{pid}/stages/reorder",
            headers=CSRF_HEADERS,
            json={"stageIds": list(reversed(ids))},
        )
        assert reordered.status_code == 200, reordered.text
    finally:
        await gerente.aclose()


async def test_tc_c_17_non_full_scope_is_forbidden(client: AsyncClient) -> None:
    payload = signup_payload()
    await signup_and_verify(client, payload)
    login = await client.post(
        "/api/v1/public/sessions",
        headers=CSRF_HEADERS,
        json={"email": payload["email"], "password": VALID_PASSWORD},
    )
    assert login.status_code == 200
    assert login.json()["status"] == "mfa_enrollment_required"
    pipelines = await client.get("/api/v1/pipelines")
    assert pipelines.status_code == 403
    deals = await client.get("/api/v1/deals")
    assert deals.status_code == 403


async def test_tc_c_18_cross_tenant_deal_is_not_found(client: AsyncClient) -> None:
    await enroll_admin(client)
    pipeline = await _default_pipeline(client)
    deal = await _create_deal(client, pipelineId=pipeline["id"])
    async with await _new_client() as other:
        await enroll_admin(other)
        fetched = await other.get(f"/api/v1/deals/{deal['id']}")
        assert fetched.status_code == 404
        assert fetched.json()["code"] == "not_found"
        missing = await other.get(f"/api/v1/deals/{uuid4()}")
        assert missing.status_code == 404
