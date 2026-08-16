from app.modules.rbac.matrix import ROLE_PERMISSIONS
from app.modules.rbac.permissions import Permission


def test_administrador_has_every_permission() -> None:
    assert set(Permission) <= ROLE_PERMISSIONS["administrador"]


def test_gerente_and_vendedor_hold_profile_and_contacts() -> None:
    base = {
        Permission.PROFILE_READ,
        Permission.PROFILE_WRITE,
        Permission.CONTACTS_READ,
        Permission.CONTACTS_WRITE,
    }
    assert base <= ROLE_PERMISSIONS["gerente"]
    assert base <= ROLE_PERMISSIONS["vendedor"]


def test_gerente_and_vendedor_hold_pipeline_reads_and_deal_writes() -> None:
    for role in ("gerente", "vendedor"):
        assert Permission.PIPELINE_READ in ROLE_PERMISSIONS[role]
        assert Permission.DEAL_WRITE in ROLE_PERMISSIONS[role]


def test_only_gerente_manages_pipelines() -> None:
    assert Permission.PIPELINE_MANAGE in ROLE_PERMISSIONS["gerente"]
    assert Permission.PIPELINE_MANAGE not in ROLE_PERMISSIONS["vendedor"]


def test_gerente_and_vendedor_lack_admin_permissions() -> None:
    for role in ("gerente", "vendedor"):
        assert Permission.USERS_INVITE not in ROLE_PERMISSIONS[role]
        assert Permission.USERS_MANAGE not in ROLE_PERMISSIONS[role]
        assert Permission.ARCO_INBOX_READ not in ROLE_PERMISSIONS[role]
        assert Permission.AUDIT_READ not in ROLE_PERMISSIONS[role]
