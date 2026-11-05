"""Seed two fake test organisations for local development and tests.

Run with ``python -m app.core.db.seed``. Idempotent: re-running changes nothing. Refuses to
run in a deployed environment. All names and addresses are fictitious (``.test`` domain).
"""

import sys
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import Connection, create_engine, inspect
from sqlalchemy.dialects.postgresql import insert

from app.core.admin.models import PlatformAdmin
from app.core.config import Settings
from app.core.modules.models import OrganizationModule
from app.core.tenancy.models import Membership, MembershipRole, Organization, User
from app.modules.catalogue.models import Price, PriceList, Product, StockLevel, Variant, VatRate
from app.modules.crm.models import Contact, Customer, CustomerKind, Lead, LeadSource, LeadStatus
from app.modules.inbox.models import (
    AuthorKind,
    Channel,
    ChannelKind,
    Conversation,
    ConversationStatus,
    DeliveryStatus,
    Event,
    EventKind,
    Handler,
    Message,
    MessageDirection,
    Participant,
    ParticipantKind,
)
from app.modules.quotations.models import (
    Counter,
    Line,
    LineKind,
    Quote,
    QuoteStatus,
    Version,
    VersionStatus,
)
from app.modules.quotations.pricing import LineInput, line_totals

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
    if inspect(connection).has_table("inbox_conversations"):
        seed_inbox(connection)
    if inspect(connection).has_table("quotations_quotes"):
        seed_quotations(connection)


def seed_catalogue(connection: Connection) -> None:
    slug, org_id = SEED_CATALOGUE_SLUG, seed_id(SEED_CATALOGUE_SLUG)
    vat_ids: dict[str, uuid.UUID] = {}
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


@dataclass(frozen=True)
class SeedMessage:
    direction: MessageDirection
    body: str
    minutes: int  # after SEED_AS_OF
    author_email: str | None = None  # staff author; None for the customer


@dataclass(frozen=True)
class SeedConversation:
    subject: str
    channel: str
    status: ConversationStatus
    messages: tuple[SeedMessage, ...]
    contact_email: str | None = None  # a seeded CRM contact
    address: str | None = None  # an unknown sender instead
    sender_name: str | None = None
    lead_title: str | None = None
    assignee_email: str | None = None


# Inbox fixtures per organisation slug: channels (name, kind) and conversations.
SEED_INBOX_CHANNELS: dict[str, tuple[tuple[str, ChannelKind], ...]] = {
    "lumen-lighting-test": (
        ("Shop phone", ChannelKind.MANUAL),
        ("Shop email", ChannelKind.EMAIL),
    ),
    "harbour-catering-test": (("Office phone", ChannelKind.MANUAL),),
}
SEED_INBOX: dict[str, tuple[SeedConversation, ...]] = {
    "lumen-lighting-test": (
        SeedConversation(
            subject="Chandelier quote follow-up",
            channel="Shop phone",
            status=ConversationStatus.WAITING_ON_CUSTOMER,
            contact_email="clara.borg@seaview.example.test",
            lead_title="Lobby chandelier replacement",
            assignee_email="olivia.owner@lumen.example.test",
            messages=(
                SeedMessage(
                    MessageDirection.INBOUND,
                    "Clara called asking when the lobby chandelier quote will be ready.",
                    0,
                ),
                SeedMessage(
                    MessageDirection.OUTBOUND,
                    "Told Clara the quote will follow by Friday once sizes are confirmed.",
                    5,
                    "olivia.owner@lumen.example.test",
                ),
            ),
        ),
        SeedConversation(
            subject="Outdoor spike lights",
            channel="Shop phone",
            status=ConversationStatus.OPEN,
            address="+35679000009",
            sender_name="Walk-in caller",
            messages=(
                SeedMessage(
                    MessageDirection.INBOUND,
                    "Caller wants six garden spike lights and asked if they are in stock.",
                    30,
                ),
            ),
        ),
    ),
    "harbour-catering-test": (
        SeedConversation(
            subject="Menu tasting date",
            channel="Office phone",
            status=ConversationStatus.OPEN,
            contact_email="nina.camilleri@valletta-events.example.test",
            messages=(
                SeedMessage(
                    MessageDirection.INBOUND, "Nina asked to book a menu tasting next week.", 10
                ),
            ),
        ),
    ),
}


def seed_inbox(connection: Connection) -> None:
    for slug, channels in SEED_INBOX_CHANNELS.items():
        org_id = seed_id(slug)
        for name, kind in channels:
            connection.execute(
                insert(Channel)
                .values(
                    id=seed_id(f"{slug}:channel:{name}"),
                    organization_id=org_id,
                    kind=kind,
                    name=name,
                )
                .on_conflict_do_nothing()
            )
    for slug, conversations in SEED_INBOX.items():
        org_id = seed_id(slug)
        for conv in conversations:
            conversation_id = seed_id(f"{slug}:conversation:{conv.subject}")
            channel_id = seed_id(f"{slug}:channel:{conv.channel}")
            contact_id = (
                seed_id(f"{slug}:contact:{conv.contact_email}") if conv.contact_email else None
            )
            last = max(m.minutes for m in conv.messages)
            connection.execute(
                insert(Conversation)
                .values(
                    id=conversation_id,
                    organization_id=org_id,
                    channel_id=channel_id,
                    subject=conv.subject,
                    status=conv.status,
                    handler=Handler.STAFF,
                    assignee_user_id=seed_id(conv.assignee_email) if conv.assignee_email else None,
                    contact_id=contact_id,
                    lead_id=seed_id(f"{slug}:lead:{conv.lead_title}") if conv.lead_title else None,
                    last_message_at=SEED_AS_OF + timedelta(minutes=last),
                    status_changed_at=SEED_AS_OF + timedelta(minutes=last),
                )
                .on_conflict_do_nothing()
            )
            connection.execute(
                insert(Event)
                .values(
                    id=seed_id(f"{slug}:conversation-event:{conv.subject}"),
                    organization_id=org_id,
                    conversation_id=conversation_id,
                    kind=EventKind.CREATED,
                    details={"channel_id": str(channel_id), "source": "seed"},
                    occurred_at=SEED_AS_OF,
                )
                .on_conflict_do_nothing()
            )
            participant_id = seed_id(f"{slug}:participant:{conv.subject}")
            connection.execute(
                insert(Participant)
                .values(
                    id=participant_id,
                    organization_id=org_id,
                    conversation_id=conversation_id,
                    kind=ParticipantKind.CONTACT if contact_id else ParticipantKind.EXTERNAL,
                    contact_id=contact_id,
                    display_name=conv.sender_name,
                    address=conv.address or conv.contact_email,
                )
                .on_conflict_do_nothing()
            )
            for index, message in enumerate(conv.messages):
                inbound = message.direction is MessageDirection.INBOUND
                connection.execute(
                    insert(Message)
                    .values(
                        id=seed_id(f"{slug}:message:{conv.subject}:{index}"),
                        organization_id=org_id,
                        conversation_id=conversation_id,
                        channel_id=channel_id,
                        direction=message.direction,
                        author_kind=AuthorKind.CUSTOMER if inbound else AuthorKind.STAFF,
                        author_user_id=seed_id(message.author_email)
                        if message.author_email
                        else None,
                        participant_id=participant_id if inbound else None,
                        body=message.body,
                        delivery_status=DeliveryStatus.RECEIVED
                        if inbound
                        else DeliveryStatus.LOGGED,
                        occurred_at=SEED_AS_OF + timedelta(minutes=message.minutes),
                    )
                    .on_conflict_do_nothing()
                )


# One draft quote for Lumen: a catalogue SKU and a custom installation line.
SEED_QUOTE_NUMBER = "Q-2026-0001"


def seed_quotations(connection: Connection) -> None:
    slug = SEED_CATALOGUE_SLUG
    org_id = seed_id(slug)
    quote_id = seed_id(f"{slug}:quote:{SEED_QUOTE_NUMBER}")
    version_id = seed_id(f"{slug}:quote:{SEED_QUOTE_NUMBER}:v1")
    contact_id = seed_id(f"{slug}:contact:clara.borg@seaview.example.test")
    vat_id = seed_id(f"{slug}:vat:STANDARD")
    connection.execute(
        insert(Counter)
        .values(organization_id=org_id, year=2026, last_number=1)
        .on_conflict_do_nothing()
    )
    connection.execute(
        insert(Quote)
        .values(
            id=quote_id,
            organization_id=org_id,
            number=SEED_QUOTE_NUMBER,
            title="Lobby chandelier replacement",
            contact_id=contact_id,
            customer_id=seed_id(f"{slug}:customer:Seaview Hotel (test)"),
            lead_id=seed_id(f"{slug}:lead:Lobby chandelier replacement"),
            price_list_id=seed_id(f"{slug}:price-list:{SEED_PRICE_LIST[0]}"),
            status=QuoteStatus.DRAFT,
            current_version=1,
            created_by_user_id=seed_id("olivia.owner@lumen.example.test"),
        )
        .on_conflict_do_nothing()
    )
    connection.execute(
        insert(Version)
        .values(
            id=version_id,
            organization_id=org_id,
            quote_id=quote_id,
            version=1,
            status=VersionStatus.DRAFT,
            prices_include_vat=True,
        )
        .on_conflict_do_nothing()
    )
    lines = (
        (
            LineKind.CATALOGUE,
            "ARC-P-30-BRS",
            "Arc pendant light - 30 cm, brass",
            2,
            12900,
            Decimal("0"),
        ),
        (LineKind.CUSTOM, None, "Installation (half day)", 1, 8000, Decimal("0")),
    )
    for position, (kind, sku, description, quantity, price, discount) in enumerate(lines, 1):
        totals = line_totals(
            LineInput(price, quantity, discount, "STANDARD", Decimal("18.00")),
            prices_include_vat=True,
        )
        connection.execute(
            insert(Line)
            .values(
                id=seed_id(f"{slug}:quote:{SEED_QUOTE_NUMBER}:line:{position}"),
                organization_id=org_id,
                version_id=version_id,
                position=position,
                kind=kind,
                variant_id=seed_id(f"{slug}:sku:{sku}") if sku else None,
                sku=sku,
                description=description,
                quantity=quantity,
                unit_price_minor=price,
                source_price_id=seed_id(f"{slug}:price:{sku}") if sku else None,
                price_valid_from=SEED_AS_OF if sku else None,
                vat_rate_id=vat_id,
                vat_code="STANDARD",
                vat_percent=Decimal("18.00"),
                discount_percent=discount,
                net_minor=totals.net_minor,
                vat_minor=totals.vat_minor,
                gross_minor=totals.gross_minor,
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
