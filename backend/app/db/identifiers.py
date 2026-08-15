import re
from uuid import UUID

SCHEMA_NAME_RE = re.compile(r"^t_[0-9a-f]{32}$")


def schema_name_for(tenant_id: UUID) -> str:
    return "t_" + tenant_id.hex
