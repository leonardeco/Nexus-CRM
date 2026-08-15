from sqlalchemy import text

from app.db.identifiers import SCHEMA_NAME_RE


async def set_search_path(conn, schema_name: str) -> None:
    if SCHEMA_NAME_RE.match(schema_name) is None:
        raise ValueError(f"invalid schema name: {schema_name}")
    path = f"{schema_name}, catalog"
    await conn.execute(
        text("SELECT set_config('search_path', :path, true)"),
        {"path": path},
    )
