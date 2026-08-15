import asyncio
import json
import logging
from uuid import UUID

from redis.asyncio import Redis
from sqlalchemy import text

from app.core.config import settings
from app.db.engine import SessionLocal
from app.modules.emailing import outbox
from app.modules.emailing.mailer import send_email
from app.modules.tenancy.provisioner import TenantProvisioner

JOBS_KEY = "nexus:jobs"
log = logging.getLogger("nexus.worker")


async def enqueue_job(redis: Redis, job_type: str, payload: dict) -> None:
    await redis.rpush(JOBS_KEY, json.dumps({"type": job_type, "payload": payload}))


async def send_due_mail() -> None:
    async with SessionLocal() as session:
        due = await outbox.fetch_due(session)
        for message in due:
            if message.payload.get("token_hash") and "token" not in message.payload:
                await outbox.mark_sent(session, message.id)
                continue
            subject = str(message.payload.get("subject") or message.template)
            body = str(message.payload.get("body") or "")
            try:
                await asyncio.to_thread(
                    send_email,
                    message.to_email,
                    subject,
                    body,
                    message.template,
                )
                await outbox.mark_sent(session, message.id)
            except Exception as exc:
                log.exception("send_mail failed for %s", message.id)
                await outbox.mark_failed(session, message.id, str(exc))
        await session.commit()


async def provision_tenant(tenant_id: UUID) -> None:
    async with SessionLocal() as session:
        provisioner = TenantProvisioner(session)
        tenant = await provisioner.provision(tenant_id)
        tenant.status = "active"
        await session.commit()


async def provision_pending() -> None:
    async with SessionLocal() as session:
        result = await session.execute(
            text("SELECT id FROM catalog.tenants WHERE status = 'provisioning'")
        )
        ids = [row[0] for row in result]
    for tenant_id in ids:
        try:
            await provision_tenant(tenant_id)
        except Exception:
            log.exception("provision_tenant failed for %s", tenant_id)


async def handle_job(job: dict) -> None:
    job_type = job.get("type")
    payload = job.get("payload") or {}
    if job_type == "send_mail":
        await send_due_mail()
    elif job_type == "provision_tenant":
        await provision_tenant(UUID(str(payload["tenant_id"])))
    else:
        log.warning("unknown job type: %s", job_type)


async def run() -> None:
    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    try:
        while True:
            try:
                item = await redis.blpop(JOBS_KEY, timeout=5)
                if item is not None:
                    _, raw = item
                    await handle_job(json.loads(raw))
                await send_due_mail()
                await provision_pending()
            except Exception:
                log.exception("worker loop error")
                await asyncio.sleep(1)
    finally:
        await redis.aclose()


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run())


if __name__ == "__main__":
    main()
