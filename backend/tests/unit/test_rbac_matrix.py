from app.modules.rbac.matrix import ROLE_PERMISSIONS
from app.modules.rbac.permissions import Permission


def test_administrador_has_every_permission() -> None:
    assert set(Permission) <= ROLE_PERMISSIONS["administrador"]


def test_gerente_and_vendedor_hold_profile_and_contacts() -> None:
    expected = {
        Permission.PROFILE_READ,
        Permission.PROFILE_WRITE,
        Permission.CONTACTS_READ,
        Permission.CONTACTS_WRITE,
    }
    assert ROLE_PERMISSIONS["gerente"] == expected
    assert ROLE_PERMISSIONS["vendedor"] == expected


def test_gerente_and_vendedor_lack_admin_permissions() -> None:
    for role in ("gerente", "vendedor"):
        assert Permission.USERS_INVITE not in ROLE_PERMISSIONS[role]
        assert Permission.USERS_MANAGE not in ROLE_PERMISSIONS[role]
        assert Permission.ARCO_INBOX_READ not in ROLE_PERMISSIONS[role]
        assert Permission.AUDIT_READ not in ROLE_PERMISSIONS[role]
