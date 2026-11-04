"""Local only: give a signed-in profile a role in a seeded workspace.

Usage: ``python -m app.core.db.dev_grant you@example.com lumen-lighting-test owner``.
Sign in once first so your profile exists. Refuses in deployed environments.
"""

import sys

from sqlalchemy import create_engine, select
from sqlalchemy.dialects.postgresql import insert

from app.core.config import Settings
from app.core.db.seed import SeedRefusedError
from app.core.tenancy.models import Membership, MembershipRole, Organization, User


def grant(settings: Settings, email: str, slug: str, role: MembershipRole) -> None:
    if settings.is_deployed:
        raise SeedRefusedError(f"Refusing to grant roles in {settings.environment!r}.")
    engine = create_engine(settings.require_migration_database_url())
    try:
        with engine.begin() as conn:
            user_id = conn.scalar(select(User.id).where(User.email == email))
            org_id = conn.scalar(select(Organization.id).where(Organization.slug == slug))
            if user_id is None:
                raise SystemExit(f"No profile for {email}; sign in to the platform once first.")
            if org_id is None:
                raise SystemExit(f"No workspace {slug!r}; run `make db-seed`.")
            conn.execute(
                insert(Membership)
                .values(organization_id=org_id, user_id=user_id, role=role)
                .on_conflict_do_update(
                    index_elements=["organization_id", "user_id"], set_={"role": role}
                )
            )
    finally:
        engine.dispose()


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print(__doc__)
        return 2
    email, slug, role = argv
    grant(Settings(), email, slug, MembershipRole(role))
    print(f"{email} is now {role} of {slug}.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
