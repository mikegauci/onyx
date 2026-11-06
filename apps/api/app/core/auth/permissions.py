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
    CRM_READ = "crm.read"
    CRM_WRITE = "crm.write"  # create/edit customers, contacts and leads; notes; lead status
    CRM_IMPORT = "crm.import"
    CRM_ARCHIVE = "crm.archive"
    CATALOGUE_READ = "catalogue.read"
    CATALOGUE_IMPORT = "catalogue.import"
    CATALOGUE_MANAGE = "catalogue.manage"  # VAT rates, price lists, archiving products/SKUs
    INBOX_READ = "inbox.read"
    INBOX_WRITE = "inbox.write"  # log messages and notes; assign, status, handoff to staff
    INBOX_MANAGE = "inbox.manage"  # channels; handing conversations to the assistant
    QUOTATIONS_READ = "quotations.read"
    QUOTATIONS_WRITE = "quotations.write"  # draft, edit, revise, record outcome, cancel
    QUOTATIONS_APPROVE = "quotations.approve"  # approve; discounts above the policy limit
    QUOTATIONS_MANAGE = "quotations.manage"  # numbering, validity and discount policy
    AI_USAGE_READ = "ai.usage.read"  # the workspace's AI spend, budget and call history


_MEMBER = frozenset(
    {
        Permission.WORKSPACE_READ,
        Permission.CRM_READ,
        Permission.CRM_WRITE,
        Permission.CATALOGUE_READ,
        Permission.INBOX_READ,
        Permission.INBOX_WRITE,
        Permission.QUOTATIONS_READ,
        Permission.QUOTATIONS_WRITE,
    }
)
_ADMIN = _MEMBER | {
    Permission.WORKSPACE_UPDATE,
    Permission.MEMBERS_READ,
    Permission.INVITATIONS_CREATE,
    Permission.AUDIT_READ,
    Permission.CRM_IMPORT,
    Permission.CRM_ARCHIVE,
    Permission.CATALOGUE_IMPORT,
    Permission.CATALOGUE_MANAGE,
    Permission.INBOX_MANAGE,
    Permission.QUOTATIONS_APPROVE,
    Permission.QUOTATIONS_MANAGE,
    Permission.AI_USAGE_READ,
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
