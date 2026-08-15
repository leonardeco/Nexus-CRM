import json
import os
import re
from collections.abc import AsyncIterator
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from uuid import uuid4

os.environ["NEXUS_DATA_KEY"] = "0123456789abcdef0123456789abcdef"
os.environ["SESSION_COOKIE_SECURE"] = "false"

from tests._bootstrap_local import ensure_local_services

ensure_local_services()

import pyotp
import pytest
from alembic import command
from alembic.config import Config
from fakeredis import FakeAsyncRedis
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from app.db.engine import engine
from app.db.identifiers import SCHEMA_NAME_RE
from app.main import app
from app.modules.rbac.deps import get_redis

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = REPO_ROOT / "backend"
CSRF_HEADERS = {"X-Nexus-Client": "web"}
VALID_PASSWORD = "ValidPass1x"

_shared_redis: FakeAsyncRedis | None = None
_captured_mail: list[dict[str, str]] = []
_TOKEN_RE = re.compile(r"Token:\s+(\S+)")


def _run_catalog_migrations() -> None:
    cfg = Config(str(BACKEND_ROOT / "alembic.ini"))
    command.upgrade(cfg, "head")


@pytest.fixture(scope="session", autouse=True)
def apply_catalog_migrations() -> None:
    _run_catalog_migrations()


@pytest.fixture(scope="session", autouse=True)
async def fake_redis_override() -> AsyncIterator[None]:
    global _shared_redis
    _shared_redis = FakeAsyncRedis(decode_responses=True)

    async def _override() -> AsyncIterator[FakeAsyncRedis]:
        assert _shared_redis is not None
        yield _shared_redis

    app.dependency_overrides[get_redis] = _override
    yield
    app.dependency_overrides.pop(get_redis, None)
    await _shared_redis.aclose()
    _shared_redis = None


async def _flush_redis() -> None:
    if _shared_redis is not None:
        await _shared_redis.flushdb()


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture(autouse=True)
def capture_smtp(monkeypatch: pytest.MonkeyPatch) -> None:
    _captured_mail.clear()

    def _fake_send(
        to_email: str, subject: str, body: str, template: str = ""
    ) -> None:
        _captured_mail.append(
            {
                "to": to_email,
                "subject": subject,
                "body": body,
                "template": template,
            }
        )

    monkeypatch.setattr("app.modules.emailing.outbox.send_email", _fake_send)
    monkeypatch.setattr("app.modules.emailing.mailer.send_email", _fake_send)


@pytest.fixture(autouse=True)
async def reset_state() -> AsyncIterator[None]:
    await _flush_redis()
    yield
    await _flush_redis()
    try:
        async with engine.begin() as conn:
            namespaces = (
                await conn.execute(
                    text("SELECT nspname FROM pg_namespace WHERE nspname LIKE 't_%'")
                )
            ).scalars()
            for name in namespaces:
                if SCHEMA_NAME_RE.match(name):
                    await conn.execute(text(f'DROP SCHEMA "{name}" CASCADE'))
            await conn.execute(text("TRUNCATE TABLE catalog.tenants CASCADE"))
    except Exception:
        pass


def unique_email() -> str:
    return f"admin-{uuid4().hex[:12]}@example.com"


def unique_slug() -> str:
    return f"acme-{uuid4().hex[:8]}"


def signup_payload(**overrides: object) -> dict[str, object]:
    body: dict[str, object] = {
        "companyName": "Acme SAS",
        "slug": unique_slug(),
        "adminFullName": "Ana Pérez",
        "email": unique_email(),
        "password": VALID_PASSWORD,
        "acceptPrivacyPolicy": True,
        "acceptHabeasData": True,
        "policyVersion": "privacy-2026-08-01",
    }
    body.update(overrides)
    return body


async def outbox_token(email: str, template: str) -> str:
    matches = [
        item
        for item in _captured_mail
        if item["to"].lower() == email.lower() and item["template"] == template
    ]
    assert matches, f"no captured SMTP token for {email} {template}"
    body = matches[-1]["body"]
    found = _TOKEN_RE.search(body)
    assert found is not None, body
    token = found.group(1)
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
        payload = json.loads(payload)
    assert isinstance(payload, dict)
    assert "token" not in payload
    assert token not in json.dumps(payload)
    return token


async def outbox_count(email: str, template: str) -> int:
    async with engine.connect() as conn:
        count = await conn.scalar(
            text(
                """
                SELECT count(*) FROM catalog.email_outbox
                WHERE lower(to_email) = lower(:email)
                  AND template = :template
                """
            ),
            {"email": email, "template": template},
        )
    return int(count or 0)


async def signup_and_verify(client: AsyncClient, payload: dict[str, object]) -> None:
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


async def enroll_admin(client: AsyncClient) -> dict[str, object]:
    payload = signup_payload()
    await signup_and_verify(client, payload)
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
    return {
        "signup": payload,
        "me": me.json(),
        "secret": secret,
        "backupCodes": confirm.json()["backupCodes"],
    }
