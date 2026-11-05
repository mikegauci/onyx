"""Domain permissions and the roles that hold them. Checked on the server for every action.

Routes ask for a permission, never a role, so roles can change without touching routes. The
frontend may read a caller's permissions to hide actions, but only this module decides.
"""

import enum

from app.core.tenancy.models import MembershipRole


class Permission(enum.StrEnum):
    WORKSPACE_READ = "workspace.read"
    WORKSPACE_UPDATE = "workspace.update"
    MEMBERS_READ = "members.read"
    INVITATIONS_CREATE = "invitations.create"
    AUDIT_READ = "audit.read"


_MEMBER = frozenset({Permission.WORKSPACE_READ})
_ADMIN = _MEMBER | {
    Permission.WORKSPACE_UPDATE,
    Permission.MEMBERS_READ,
    Permission.INVITATIONS_CREATE,
    Permission.AUDIT_READ,
}

ROLE_PERMISSIONS: dict[MembershipRole, frozenset[Permission]] = {
    MembershipRole.MEMBER: _MEMBER,
    MembershipRole.ADMIN: _ADMIN,
    MembershipRole.OWNER: _ADMIN,
}


def has_permission(role: MembershipRole, permission: Permission) -> bool:
    return permission in ROLE_PERMISSIONS[role]


def permissions_for(role: MembershipRole) -> list[Permission]:
    return sorted(ROLE_PERMISSIONS[role])
