from fastapi import FastAPI
from redis.asyncio import Redis
from sqlalchemy import text

from app.core.config import settings
from app.core.csrf import CsrfMiddleware
from app.core.errors import register_errors
from app.core.rate_limit import redis_unavailable_error
from app.db.engine import engine
from app.modules.arco.router import router as arco_router
from app.modules.audit.router import router as audit_router
from app.modules.identity.router import router as identity_router

app = FastAPI(title="NEXUS CRM")
register_errors(app)
app.add_middleware(CsrfMiddleware)
app.include_router(identity_router)
app.include_router(arco_router)
app.include_router(audit_router)


@app.get("/api/v1/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/v1/readyz")
async def readyz() -> dict[str, str]:
    redis = Redis.from_url(settings.redis_url)
    try:
        await redis.ping()
    except Exception as exc:
        raise redis_unavailable_error() from exc
    finally:
        await redis.aclose()
    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))
    return {"status": "ok"}
