import asyncio
import logging
from argparse import Namespace
from pathlib import Path
from uuid import UUID, uuid4

from alembic import command
from alembic.config import Config
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.identifiers import SCHEMA_NAME_RE, schema_name_for
from app.modules.identity.models import User
from app.modules.tenancy.models import Tenant

log = logging.getLogger("nexus.provisioner")


def _backend_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _alembic_config(tenant_schema: str) -> Config:
    ini = _backend_root() / "alembic.ini"
    alembic_dir = ini.parent / "alembic"
    cfg = Config(str(ini))
    cfg.set_main_option("script_location", str(alembic_dir))
    cfg.set_main_option("version_locations", str(alembic_dir / "tenant" / "versions"))
    cfg.set_main_option("prepend_sys_path", str(ini.parent))
    cfg.cmd_opts = Namespace(x=[f"tenant_schema={tenant_schema}"])
    return cfg


def _run_tenant_upgrade(schema_name: str) -> None:
    command.upgrade(_alembic_config(schema_name), "head")


def _quoted_schema(schema_name: str) -> str:
    if SCHEMA_NAME_RE.match(schema_name) is None:
        raise ValueError(f"invalid schema name: {schema_name}")
    return f'"{schema_name}"'


class TenantProvisioner:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def provision(
        self,
        tenant_id: UUID | None = None,
        *,
        slug: str | None = None,
        company_name: str | None = None,
    ) -> Tenant:
        tenant_id = tenant_id or uuid4()
        tenant = await self._session.get(Tenant, tenant_id)
        if tenant is None:
            if slug is None or company_name is None:
                raise ValueError("slug and company_name are required to insert a tenant")
            tenant = Tenant(
                id=tenant_id,
                slug=slug,
                company_name=company_name,
                schema_name=schema_name_for(tenant_id),
                plan="starter",
                seat_cap=2,
                status="provisioning",
            )
            self._session.add(tenant)
        else:
            if SCHEMA_NAME_RE.match(tenant.schema_name) is None:
                tenant.schema_name = schema_name_for(tenant.id)
            if tenant.status != "active":
                tenant.status = "provisioning"
        await self._session.flush()
        schema_name = tenant.schema_name
        quoted = _quoted_schema(schema_name)
        try:
            await self._session.execute(text(f"CREATE SCHEMA IF NOT EXISTS {quoted}"))
            await self._session.commit()
            await asyncio.to_thread(_run_tenant_upgrade, schema_name)
        except Exception:
            await self._session.rollback()
            await self.rollback(tenant_id)
            raise
        await self._session.refresh(tenant)
        return tenant

    async def rollback(self, tenant_id: UUID) -> None:
        users = await self._session.scalar(
            select(func.count()).select_from(User).where(User.tenant_id == tenant_id)
        )
        if int(users or 0) > 0:
            log.warning("skip schema drop; tenant %s already has users", tenant_id)
            tenant = await self._session.get(Tenant, tenant_id)
            if tenant is not None and tenant.status == "active":
                pass
            elif tenant is not None:
                tenant.status = "provisioning"
            await self._session.commit()
            return
        schema_name = schema_name_for(tenant_id)
        quoted = _quoted_schema(schema_name)
        await self._session.execute(text(f"DROP SCHEMA IF EXISTS {quoted} CASCADE"))
        tenant = await self._session.get(Tenant, tenant_id)
        if tenant is not None:
            await self._session.delete(tenant)
        await self._session.commit()
