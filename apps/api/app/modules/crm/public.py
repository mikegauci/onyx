"""The CRM's public read interface for other modules (inbox now; quotations later).

Other modules call these functions instead of querying CRM models, so the CRM can change its
tables without breaking them. Every function takes the bound ``TenantContext`` and filters on
it explicitly, on top of row-level security. Results carry only what callers need.
"""

import uuid
from collections.abc import Iterable
from dataclasses import dataclass

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db.context import TenantContext
from app.modules.crm.models import Contact, Lead


@dataclass(frozen=True)
class ContactSummary:
    id: uuid.UUID
    full_name: str
    email: str | None
    phone: str | None
    archived: bool


@dataclass(frozen=True)
class LeadSummary:
    id: uuid.UUID
    title: str
    contact_id: uuid.UUID
    archived: bool


def _contact(contact: Contact) -> ContactSummary:
    return ContactSummary(
        id=contact.id,
        full_name=contact.full_name,
        email=contact.email,
        phone=contact.phone,
        archived=contact.archived_at is not None,
    )


async def find_contact_by_identity(
    db: AsyncSession, tenant: TenantContext, *, email: str | None, phone: str | None
) -> ContactSummary | None:
    """The active contact with this normalised email (preferred) or phone, if any."""
    if email is None and phone is None:
        return None
    matches = []
    if email is not None:
        matches.append(Contact.email == email)
    if phone is not None:
        matches.append(Contact.phone == phone)
    rows = (
        await db.scalars(
            select(Contact).where(
                Contact.organization_id == tenant.organization_id,
                Contact.archived_at.is_(None),
                or_(*matches),
            )
        )
    ).all()
    by_email = next((c for c in rows if email is not None and c.email == email), None)
    found = by_email or next(iter(rows), None)
    return _contact(found) if found is not None else None


async def get_contacts(
    db: AsyncSession, tenant: TenantContext, ids: Iterable[uuid.UUID]
) -> dict[uuid.UUID, ContactSummary]:
    wanted = set(ids)
    if not wanted:
        return {}
    rows = await db.scalars(
        select(Contact).where(
            Contact.organization_id == tenant.organization_id, Contact.id.in_(wanted)
        )
    )
    return {c.id: _contact(c) for c in rows}


async def get_lead(
    db: AsyncSession, tenant: TenantContext, lead_id: uuid.UUID
) -> LeadSummary | None:
    lead = await db.scalar(
        select(Lead).where(Lead.organization_id == tenant.organization_id, Lead.id == lead_id)
    )
    if lead is None:
        return None
    return LeadSummary(
        id=lead.id,
        title=lead.title,
        contact_id=lead.contact_id,
        archived=lead.archived_at is not None,
    )
