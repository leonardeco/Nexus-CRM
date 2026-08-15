from app.db.identifiers import SCHEMA_NAME_RE, schema_name_for
from uuid import UUID

def test_schema_name_format() -> None:
    tid = UUID("12345678123456781234567812345678")
    name = schema_name_for(tid)
    assert name == "t_12345678123456781234567812345678"
    assert SCHEMA_NAME_RE.match(name)
    assert SCHEMA_NAME_RE.match("catalog") is None
    assert SCHEMA_NAME_RE.match("t_;drop") is None
