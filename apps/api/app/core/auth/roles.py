"""Role hierarchy: owner > admin > member."""

from app.core.tenancy.models import MembershipRole

ROLE_RANK: dict[MembershipRole, int] = {
    MembershipRole.MEMBER: 1,
    MembershipRole.ADMIN: 2,
    MembershipRole.OWNER: 3,
}


def has_at_least(role: MembershipRole, minimum: MembershipRole) -> bool:
    return ROLE_RANK[role] >= ROLE_RANK[minimum]


def can_grant(granter: MembershipRole, granted: MembershipRole) -> bool:
    """Admins grant admin/member; only owners grant owner."""
    if not has_at_least(granter, MembershipRole.ADMIN):
        return False
    return granted is not MembershipRole.OWNER or granter is MembershipRole.OWNER
