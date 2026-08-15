"""Start local Postgres (pgserver) and Redis (fakeredis) when Docker is unavailable."""

from __future__ import annotations

import asyncio
import os
import socket
import threading
from pathlib import Path

_ARTIFACTS = Path(r"C:\Users\MI PC\.config\hydraia\artifacts\crm-e2df1f")
_PGDATA = _ARTIFACTS / ".pgdata"
_REDIS_PORT = 6379

_pg_server = None
_redis_server = None


def _port_open(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.4)
        return sock.connect_ex((host, port)) == 0


async def _prepare_database(sync_uri: str) -> str:
    import asyncpg

    conn = await asyncpg.connect(sync_uri)
    try:
        roles = await conn.fetchval(
            "SELECT 1 FROM pg_roles WHERE rolname = 'nexus'"
        )
        if roles is None:
            await conn.execute("CREATE USER nexus WITH PASSWORD 'nexus' SUPERUSER")
        db = await conn.fetchval(
            "SELECT 1 FROM pg_database WHERE datname = 'nexus'"
        )
        if db is None:
            await conn.execute("CREATE DATABASE nexus OWNER nexus")
    finally:
        await conn.close()

    parsed_host = sync_uri.split("@", 1)[1]
    hostport = parsed_host.split("/", 1)[0]
    nexus_uri = f"postgresql://nexus:nexus@{hostport}/nexus"
    conn = await asyncpg.connect(nexus_uri)
    try:
        for ext in ("pgcrypto", "citext"):
            try:
                await conn.execute(f"CREATE EXTENSION IF NOT EXISTS {ext}")
            except asyncpg.exceptions.FeatureNotSupportedError:
                pass
        await conn.execute("CREATE SCHEMA IF NOT EXISTS catalog")
    finally:
        await conn.close()
    return nexus_uri.replace("postgresql://", "postgresql+asyncpg://", 1)


def ensure_local_services() -> None:
    global _pg_server, _redis_server

    if os.environ.get("DATABASE_URL", "").startswith("postgresql") and _port_open(
        "127.0.0.1", 5432
    ):
        os.environ.setdefault(
            "DATABASE_URL",
            "postgresql+asyncpg://nexus:nexus@localhost:5432/nexus",
        )
    else:
        import pgserver

        _PGDATA.parent.mkdir(parents=True, exist_ok=True)
        if not _PGDATA.exists():
            _PGDATA.mkdir()
        _pg_server = pgserver.get_server(_PGDATA, cleanup_mode=None)
        sync_uri = _pg_server.get_uri()
        os.environ["DATABASE_URL"] = asyncio.run(_prepare_database(sync_uri))

    if not _port_open("127.0.0.1", _REDIS_PORT):
        from fakeredis import TcpFakeServer

        _redis_server = TcpFakeServer(
            ("127.0.0.1", _REDIS_PORT), server_type="redis"
        )
        _redis_server.daemon_threads = True
        thread = threading.Thread(target=_redis_server.serve_forever, daemon=True)
        thread.start()
    os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
    os.environ.setdefault("SMTP_URL", "smtp://localhost:1025")
    os.environ.setdefault(
        "NEXUS_DATA_KEY", "0123456789abcdef0123456789abcdef"
    )
    os.environ.setdefault("SESSION_COOKIE_SECURE", "false")
    os.environ.setdefault("CURRENT_POLICY_VERSION", "privacy-2026-08-01")
