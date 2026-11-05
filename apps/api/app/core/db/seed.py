"""Seed two fake test organisations for local development and tests.

Run with ``python -m app.core.db.seed``. Idempotent: re-running changes nothing. Refuses to
run in a deployed environment. All names and addresses are fictitious (``.test`` domain).
"""

import sys
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import Connection, create_engine, inspect
from sqlalchemy.dialects.postgresql import insert

from app.core.admin.models import PlatformAdmin
from app.core.config import Settings
from app.core.modules.models import OrganizationModule
from app.core.tenancy.models import Membership, MembershipRole, Organization, User
from app.modules.catalogue.models import Price, PriceList, Product, StockLevel, Variant, VatRate
from app.modules.crm.models import Contact, Customer, CustomerKind, Lead, LeadSource, LeadStatus

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


@dataclass(frozen=True)
class SeedLead:
    title: str
    status: LeadStatus


@dataclass(frozen=True)
class SeedContact:
    full_name: str
    email: str
    phone: str
    leads: tuple[SeedLead, ...] = ()


# CRM fixtures per organisation slug: customer name -> its contacts (None: no customer).
SEED_CRM: dict[str, dict[str | None, tuple[SeedContact, ...]]] = {
    "lumen-lighting-test": {
        "Seaview Hotel (test)": (
            SeedContact(
                "Clara Borg",
                "clara.borg@seaview.example.test",
                "+35621000001",
                (SeedLead("Lobby chandelier replacement", LeadStatus.QUALIFIED),),
            ),
        ),
        None: (
            SeedContact(
                "Luca Vella",
                "luca.vella@example.test",
                "+35699000002",
                (SeedLead("Garden lighting enquiry", LeadStatus.NEW),),
            ),
        ),
    },
    "harbour-catering-test": {
        "Valletta Events (test)": (
            SeedContact(
                "Nina Camilleri",
                "nina.camilleri@valletta-events.example.test",
                "+35621000003",
                (SeedLead("Wedding catering for 120 guests", LeadStatus.NEW),),
            ),
        ),
    },
}


@dataclass(frozen=True)
class SeedVariant:
    sku: str
    name: str
    attributes: dict[str, str]
    price_minor: int | None  # None: deliberately no price ("not provided")
    stock: int | None  # None: deliberately no stock data ("unknown")


@dataclass(frozen=True)
class SeedProduct:
    code: str
    name: str
    brand: str
    category: str
    vat_code: str | None  # None: deliberately no VAT rate set
    variants: tuple[SeedVariant, ...] = field(default=())


# Catalogue fixtures (fictitious brand and products). Prices are EUR cents, VAT-inclusive.
SEED_CATALOGUE_SLUG = "lumen-lighting-test"
SEED_VAT_RATES = (
    ("STANDARD", "Standard rate (test)", Decimal("18.00")),
    ("ZERO", "Zero rate (test)", Decimal("0.00")),
)
SEED_PRICE_LIST = ("RETAIL", "Retail (test)")
SEED_AS_OF = datetime(2026, 11, 1, 8, 0, tzinfo=UTC)
SEED_PRODUCTS: tuple[SeedProduct, ...] = (
    SeedProduct(
        "ARC-PENDANT",
        "Arc pendant light",
        "Lumetta (test)",
        "Pendants",
        "STANDARD",
        (
            SeedVariant(
                "ARC-P-30-BRS", "30 cm, brass", {"diameter_cm": "30", "finish": "brass"}, 12900, 6
            ),
            SeedVariant(
                "ARC-P-45-BLK", "45 cm, black", {"diameter_cm": "45", "finish": "black"}, 16900, 0
            ),
        ),
    ),
    SeedProduct(
        "GARDEN-SPIKE",
        "Garden spike light",
        "Lumetta (test)",
        "Outdoor",
        "STANDARD",
        (
            SeedVariant(
                "GSP-7W-3000K",
                "7 W, 3000 K",
                {"wattage": "7", "colour_temp_k": "3000", "ip_rating": "IP65"},
                None,
                24,
            ),
            SeedVariant(
                "GSP-7W-4000K",
                "7 W, 4000 K",
                {"wattage": "7", "colour_temp_k": "4000", "ip_rating": "IP65"},
                3450,
                None,
            ),
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
    seed_crm(connection)
    # Older revisions (used by migration tests) have no catalogue tables yet.
    if inspect(connection).has_table("catalogue_products"):
        seed_catalogue(connection)


def seed_catalogue(connection: Connection) -> None:
    slug, org_id = SEED_CATALOGUE_SLUG, seed_id(SEED_CATALOGUE_SLUG)
    vat_ids = {}
    for code, name, rate in SEED_VAT_RATES:
        vat_ids[code] = seed_id(f"{slug}:vat:{code}")
        connection.execute(
            insert(VatRate)
            .values(
                id=vat_ids[code], organization_id=org_id, code=code, name=name, rate_percent=rate
            )
            .on_conflict_do_nothing()
        )
    price_list_id = seed_id(f"{slug}:price-list:{SEED_PRICE_LIST[0]}")
    connection.execute(
        insert(PriceList)
        .values(
            id=price_list_id,
            organization_id=org_id,
            code=SEED_PRICE_LIST[0],
            name=SEED_PRICE_LIST[1],
            prices_include_vat=True,
            is_default=True,
        )
        .on_conflict_do_nothing()
    )
    for product in SEED_PRODUCTS:
        product_id = seed_id(f"{slug}:product:{product.code}")
        connection.execute(
            insert(Product)
            .values(
                id=product_id,
                organization_id=org_id,
                code=product.code,
                name=product.name,
                brand=product.brand,
                category=product.category,
                vat_rate_id=vat_ids[product.vat_code] if product.vat_code else None,
            )
            .on_conflict_do_nothing()
        )
        for variant in product.variants:
            variant_id = seed_id(f"{slug}:sku:{variant.sku}")
            connection.execute(
                insert(Variant)
                .values(
                    id=variant_id,
                    organization_id=org_id,
                    product_id=product_id,
                    sku=variant.sku,
                    name=variant.name,
                    attributes=variant.attributes,
                )
                .on_conflict_do_nothing()
            )
            if variant.price_minor is not None:
                connection.execute(
                    insert(Price)
                    .values(
                        id=seed_id(f"{slug}:price:{variant.sku}"),
                        organization_id=org_id,
                        variant_id=variant_id,
                        price_list_id=price_list_id,
                        amount_minor=variant.price_minor,
                        valid_from=SEED_AS_OF,
                    )
                    .on_conflict_do_nothing()
                )
            if variant.stock is not None:
                connection.execute(
                    insert(StockLevel)
                    .values(
                        id=seed_id(f"{slug}:stock:{variant.sku}"),
                        organization_id=org_id,
                        variant_id=variant_id,
                        location="main",
                        quantity_available=variant.stock,
                        observed_at=SEED_AS_OF,
                    )
                    .on_conflict_do_nothing()
                )


def seed_crm(connection: Connection) -> None:
    for slug, customers in SEED_CRM.items():
        org_id = seed_id(slug)
        for customer_name, contacts in customers.items():
            customer_id = None
            if customer_name is not None:
                customer_id = seed_id(f"{slug}:customer:{customer_name}")
                connection.execute(
                    insert(Customer)
                    .values(
                        id=customer_id,
                        organization_id=org_id,
                        kind=CustomerKind.BUSINESS,
                        name=customer_name,
                    )
                    .on_conflict_do_nothing()
                )
            for contact in contacts:
                contact_id = seed_id(f"{slug}:contact:{contact.email}")
                connection.execute(
                    insert(Contact)
                    .values(
                        id=contact_id,
                        organization_id=org_id,
                        customer_id=customer_id,
                        full_name=contact.full_name,
                        email=contact.email,
                        phone=contact.phone,
                    )
                    .on_conflict_do_nothing()
                )
                for lead in contact.leads:
                    connection.execute(
                        insert(Lead)
                        .values(
                            id=seed_id(f"{slug}:lead:{lead.title}"),
                            organization_id=org_id,
                            contact_id=contact_id,
                            customer_id=customer_id,
                            title=lead.title,
                            source=LeadSource.MANUAL,
                            status=lead.status,
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
