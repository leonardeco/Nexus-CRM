import asyncio
import json
import logging
import smtplib
from email.message import EmailMessage
from urllib.parse import urlparse
from uuid import UUID

from redis.asyncio import Redis
from sqlalchemy import text

from app.core.config import settings
from app.db.engine import SessionLocal
from app.modules.emailing import outbox
from app.modules.tenancy.provisioner import TenantProvisioner

JOBS_KEY = "nexus:jobs"
log = logging.getLogger("nexus.worker")


async def enqueue_job(redis: Redis, job_type: str, payload: dict) -> None:
    await redis.rpush(JOBS_KEY, json.dumps({"type": job_type, "payload": payload}))


def _send_smtp(to_email: str, subject: str, body: str) -> None:
    parsed = urlparse(settings.smtp_url)
    host = parsed.hostname or "localhost"
    port = parsed.port or 1025
    message = EmailMessage()
    message["From"] = "noreply@localhost"
    message["To"] = to_email
    message["Subject"] = subject
    message.set_content(body)
    with smtplib.SMTP(host, port, timeout=10) as client:
        client.send_message(message)


async def send_due_mail() -> None:
    async with SessionLocal() as session:
        due = await outbox.fetch_due(session)
        for message in due:
            subject = str(message.payload.get("subject") or message.template)
            body = str(message.payload.get("body") or "")
            try:
                await asyncio.to_thread(_send_smtp, message.to_email, subject, body)
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
