from app.modules.rbac.permissions import Permission

_PROFILE = frozenset({Permission.PROFILE_READ, Permission.PROFILE_WRITE})
_CONTACTS = frozenset({Permission.CONTACTS_READ, Permission.CONTACTS_WRITE})
_PIPELINE = frozenset({Permission.PIPELINE_READ, Permission.DEAL_WRITE})

ROLE_PERMISSIONS: dict[str, frozenset[Permission]] = {
    "administrador": frozenset(Permission),
    "gerente": _PROFILE | _CONTACTS | _PIPELINE | {Permission.PIPELINE_MANAGE},
    "vendedor": _PROFILE | _CONTACTS | _PIPELINE,
}


def has_permission(role: str, permission: Permission) -> bool:
    return permission in ROLE_PERMISSIONS.get(role, frozenset())
