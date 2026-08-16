from app.modules.rbac.permissions import Permission

_PROFILE = frozenset({Permission.PROFILE_READ, Permission.PROFILE_WRITE})
_CONTACTS = frozenset({Permission.CONTACTS_READ, Permission.CONTACTS_WRITE})

ROLE_PERMISSIONS: dict[str, frozenset[Permission]] = {
    "administrador": frozenset(Permission),
    "gerente": _PROFILE | _CONTACTS,
    "vendedor": _PROFILE | _CONTACTS,
}


def has_permission(role: str, permission: Permission) -> bool:
    return permission in ROLE_PERMISSIONS.get(role, frozenset())
