"""The role → permission matrix, stated explicitly so any change is a reviewed diff."""

import pytest

from app.core.auth.permissions import ROLE_PERMISSIONS, Permission, has_permission
from app.core.tenancy.models import MembershipRole

OWNER, ADMIN, MEMBER = MembershipRole.OWNER, MembershipRole.ADMIN, MembershipRole.MEMBER

EXPECTED: dict[Permission, set[MembershipRole]] = {
    Permission.WORKSPACE_READ: {OWNER, ADMIN, MEMBER},
    Permission.WORKSPACE_UPDATE: {OWNER, ADMIN},
    Permission.MEMBERS_READ: {OWNER, ADMIN},
    Permission.INVITATIONS_CREATE: {OWNER, ADMIN},
    Permission.AUDIT_READ: {OWNER, ADMIN},
    Permission.CRM_READ: {OWNER, ADMIN, MEMBER},
    Permission.CRM_WRITE: {OWNER, ADMIN, MEMBER},
    Permission.CRM_IMPORT: {OWNER, ADMIN},
    Permission.CRM_ARCHIVE: {OWNER, ADMIN},
    Permission.CATALOGUE_READ: {OWNER, ADMIN, MEMBER},
    Permission.CATALOGUE_IMPORT: {OWNER, ADMIN},
    Permission.CATALOGUE_MANAGE: {OWNER, ADMIN},
    Permission.INBOX_READ: {OWNER, ADMIN, MEMBER},
    Permission.INBOX_WRITE: {OWNER, ADMIN, MEMBER},
    Permission.INBOX_MANAGE: {OWNER, ADMIN},
}


def test_every_permission_is_specified() -> None:
    assert set(EXPECTED) == set(Permission)
    assert set(ROLE_PERMISSIONS) == set(MembershipRole)


@pytest.mark.parametrize("permission", list(Permission))
@pytest.mark.parametrize("role", list(MembershipRole))
def test_matrix(role: MembershipRole, permission: Permission) -> None:
    assert has_permission(role, permission) is (role in EXPECTED[permission])
