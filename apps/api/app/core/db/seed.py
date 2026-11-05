"""Seed two fake test organisations for local development and tests.

Run with ``python -m app.core.db.seed``. Idempotent: re-running changes nothing. Refuses to
run in a deployed environment. All names and addresses are fictitious (``.test`` domain).
"""

import sys
import uuid
from dataclasses import dataclass

from sqlalchemy import Connection, create_engine
from sqlalchemy.dialects.postgresql import insert

from app.core.admin.models import PlatformAdmin
from app.core.config import Settings
from app.core.modules.models import OrganizationModule
from app.core.tenancy.models import Membership, MembershipRole, Organization, User

# Fixed namespace so seeded ids are stable across runs and usable in tests.
SEED_NAMESPACE = uuid.UUID("6f1c2a52-0b7e-4f7d-9a51-3c1f0e0d5a01")


def seed_id(name: str) -> uuid.UUID:
    return uuid.uuid5(SEED_NAMESPACE, name)


def seed_auth_subject(email: str) -> uuid.UUID:
    """Fake Supabase Auth subject for a seeded user. Only tests can mint tokens for it."""
    return seed_id(f"auth:{email}")


@dataclass(frozen=True)
class SeedOrganization:
    slug: str
    name: str
    modules: tuple[str, ...]
    members: tuple[tuple[str, MembershipRole], ...]  # (user email, role)


SEED_USERS: dict[str, str] = {
    "olivia.owner@lumen.example.test": "Olivia Owner",
    "adam.admin@lumen.example.test": "Adam Admin",
    "mia.member@lumen.example.test": "Mia Member",
    "hugo.owner@harbour.example.test": "Hugo Owner",
    "hana.admin@harbour.example.test": "Hana Admin",
    "max.member@harbour.example.test": "Max Member",
    # Belongs to both organisations, for workspace-selection and isolation tests.
    "sam.consultant@onyx.example.test": "Sam Consultant",
    # Platform admin with no tenant membership, for the /admin shell and its access tests.
    "pat.platform@onyx.example.test": "Pat Platform",
}

SEED_PLATFORM_ADMINS: tuple[str, ...] = ("pat.platform@onyx.example.test",)

SEED_ORGANIZATIONS: tuple[SeedOrganization, ...] = (
    SeedOrganization(
        slug="lumen-lighting-test",
        name="Lumen Lighting (test)",
        modules=("crm", "catalogue", "inbox", "quotations"),
        members=(
            ("olivia.owner@lumen.example.test", MembershipRole.OWNER),
            ("adam.admin@lumen.example.test", MembershipRole.ADMIN),
            ("mia.member@lumen.example.test", MembershipRole.MEMBER),
            ("sam.consultant@onyx.example.test", MembershipRole.MEMBER),
        ),
    ),
    SeedOrganization(
        slug="harbour-catering-test",
        name="Harbour Catering (test)",
        modules=("crm", "inbox"),
        members=(
            ("hugo.owner@harbour.example.test", MembershipRole.OWNER),
            ("hana.admin@harbour.example.test", MembershipRole.ADMIN),
            ("max.member@harbour.example.test", MembershipRole.MEMBER),
            ("sam.consultant@onyx.example.test", MembershipRole.ADMIN),
        ),
    ),
)


class SeedRefusedError(RuntimeError):
    """Raised when seeding is attempted in a deployed environment."""


def seed(connection: Connection) -> None:
    """Insert the fixtures, skipping rows that already exist. Caller owns the transaction."""
    for email, display_name in SEED_USERS.items():
        connection.execute(
            insert(User)
            .values(
                id=seed_id(email),
                auth_subject=seed_auth_subject(email),
                email=email,
                display_name=display_name,
            )
            .on_conflict_do_nothing()
        )
    for email in SEED_PLATFORM_ADMINS:
        connection.execute(
            insert(PlatformAdmin).values(user_id=seed_id(email)).on_conflict_do_nothing()
        )
    for org in SEED_ORGANIZATIONS:
        org_id = seed_id(org.slug)
        connection.execute(
            insert(Organization)
            .values(id=org_id, slug=org.slug, name=org.name)
            .on_conflict_do_nothing()
        )
        for module_key in org.modules:
            connection.execute(
                insert(OrganizationModule)
                .values(organization_id=org_id, module_key=module_key, enabled=True)
                .on_conflict_do_nothing()
            )
        for email, role in org.members:
            connection.execute(
                insert(Membership)
                .values(
                    id=seed_id(f"{org.slug}:{email}"),
                    organization_id=org_id,
                    user_id=seed_id(email),
                    role=role,
                )
                .on_conflict_do_nothing()
            )


def run(settings: Settings) -> None:
    if settings.is_deployed:
        raise SeedRefusedError(
            f"Refusing to seed test data in the {settings.environment!r} environment."
        )
    engine = create_engine(settings.require_migration_database_url())
    try:
        with engine.begin() as connection:
            seed(connection)
    finally:
        engine.dispose()


def main() -> int:
    run(Settings())
    print(f"Seeded {len(SEED_ORGANIZATIONS)} organisations and {len(SEED_USERS)} users.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
