import os
import os
from collections.abc import AsyncIterator
from pathlib import Path
from uuid import uuid4

from tests._bootstrap_local import ensure_local_services

ensure_local_services()

import pytest
from alembic import command
from alembic.config import Config
from httpx import ASGITransport, AsyncClient
from redis.asyncio import Redis
from sqlalchemy import text

from app.db.engine import engine
from app.db.identifiers import SCHEMA_NAME_RE
from app.main import app

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = REPO_ROOT / "backend"
CSRF_HEADERS = {"X-Nexus-Client": "web"}
VALID_PASSWORD = "ValidPass1x"


def _run_catalog_migrations() -> None:
    cfg = Config(str(BACKEND_ROOT / "alembic.ini"))
    command.upgrade(cfg, "head")


@pytest.fixture(scope="session", autouse=True)
def apply_catalog_migrations() -> None:
    _run_catalog_migrations()


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture(autouse=True)
async def reset_state() -> AsyncIterator[None]:
    yield
    try:
        redis = Redis.from_url(os.environ["REDIS_URL"], decode_responses=True)
        try:
            await redis.flushdb()
        finally:
            await redis.aclose()
    except Exception:
        pass
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
