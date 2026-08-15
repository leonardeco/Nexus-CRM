import asyncio
from logging.config import fileConfig
from pathlib import Path
import sys

from alembic import context
from sqlalchemy import text
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.core.config import settings
from app.db.identifiers import SCHEMA_NAME_RE

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

x_args = context.get_x_argument(as_dictionary=True)
tenant_schema = x_args.get("tenant_schema")


def _search_path() -> str:
    if tenant_schema:
        if SCHEMA_NAME_RE.match(tenant_schema) is None:
            raise ValueError(f"invalid schema name: {tenant_schema}")
        return f"{tenant_schema}, catalog"
    return "catalog"


def run_migrations_offline() -> None:
    url = settings.database_url
    context.configure(
        url=url,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        version_table="alembic_version",
        version_table_schema=tenant_schema or "catalog",
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    path = _search_path()
    version_table_schema = tenant_schema or "catalog"
    context.configure(
        connection=connection,
        version_table="alembic_version",
        version_table_schema=version_table_schema,
        include_schemas=True,
    )
    with context.begin_transaction():
        connection.execute(
            text("SELECT set_config('search_path', :path, true)"),
            {"path": path},
        )
        context.run_migrations()


async def run_async_migrations() -> None:
    connectable = create_async_engine(settings.database_url)
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
