from app.modules.rbac.matrix import ROLE_PERMISSIONS
from app.modules.rbac.permissions import Permission


def test_administrador_has_every_permission() -> None:
    assert set(Permission) <= ROLE_PERMISSIONS["administrador"]


def test_gerente_and_vendedor_are_profile_only() -> None:
    profile = {Permission.PROFILE_READ, Permission.PROFILE_WRITE}
    assert ROLE_PERMISSIONS["gerente"] == profile
    assert ROLE_PERMISSIONS["vendedor"] == profile
    assert Permission.USERS_INVITE not in ROLE_PERMISSIONS["gerente"]
    assert Permission.USERS_MANAGE not in ROLE_PERMISSIONS["gerente"]
    assert Permission.USERS_INVITE not in ROLE_PERMISSIONS["vendedor"]
