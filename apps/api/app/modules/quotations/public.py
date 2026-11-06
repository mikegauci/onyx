"""The quotations module's public interface for other modules (assistant and outbound).

``draft_quote`` creates a **draft** quote through the normal service, so numbering, price
snapshots, VAT and totals are computed exactly as for staff-made quotes. Drafts are never sent
and must be approved by staff. ``quote_state`` tells the outbound module (PR-016) whether a
quote is approved, which version, and until when, so a reply only goes out with an approved,
valid quote.
"""

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth.deps import WorkspaceAccess
from app.core.db.context import TenantContext
from app.modules.quotations import schemas
from app.modules.quotations.models import Quote, Version, VersionStatus
from app.modules.quotations.service import QuotationService, workspace_today

__all__ = [
    "DraftLine",
    "DraftQuote",
    "QuoteState",
    "draft_quote",
    "quote_numbers",
    "quote_state",
    "workspace_today",
]


@dataclass(frozen=True)
class DraftLine:
    sku: str
    quantity: int


@dataclass(frozen=True)
class DraftQuote:
    id: uuid.UUID
    number: str


async def draft_quote(
    db: AsyncSession,
    workspace: WorkspaceAccess,
    *,
    title: str,
    contact_id: uuid.UUID,
    lead_id: uuid.UUID | None,
    lines: Sequence[DraftLine],
) -> DraftQuote:
    """A draft on the default price list, one catalogue line per SKU, with no discounts."""
    service = QuotationService(db, workspace)
    quote_id = await service.create_quote(
        schemas.QuoteCreate(title=title[:200], contact_id=contact_id, lead_id=lead_id)
    )
    for line in lines:
        await service.add_line(
            quote_id,
            schemas.CatalogueLineCreate(kind="catalogue", sku=line.sku, quantity=line.quantity),
        )
    number = await db.scalar(
        select(Quote.number).where(
            Quote.organization_id == workspace.tenant.organization_id, Quote.id == quote_id
        )
    )
    return DraftQuote(id=quote_id, number=str(number))


async def quote_numbers(
    db: AsyncSession, tenant: TenantContext, quote_ids: Sequence[uuid.UUID]
) -> dict[uuid.UUID, str]:
    """Quote numbers by id, for quotes in this tenant."""
    if not quote_ids:
        return {}
    rows = await db.execute(
        select(Quote.id, Quote.number).where(
            Quote.organization_id == tenant.organization_id, Quote.id.in_(list(quote_ids))
        )
    )
    return {row.id: row.number for row in rows}


@dataclass(frozen=True)
class QuoteState:
    id: uuid.UUID
    number: str
    contact_id: uuid.UUID
    status: str  # QuoteStatus value
    version: int  # the current version number
    version_approved: bool  # the current version is approved and frozen
    valid_until: date | None


async def quote_state(
    db: AsyncSession, tenant: TenantContext, quote_id: uuid.UUID, *, lock: bool = False
) -> QuoteState | None:
    """The quote's state now, or None if it is not in this tenant.

    With ``lock`` the quote row is share-locked until the transaction ends, so it cannot be
    revised, cancelled or decided while a reply that includes it is being sent.
    """
    query = select(Quote).where(
        Quote.organization_id == tenant.organization_id, Quote.id == quote_id
    )
    if lock:
        query = query.with_for_update(read=True).execution_options(populate_existing=True)
    quote = await db.scalar(query)
    if quote is None:
        return None
    version = await db.scalar(
        select(Version).where(
            Version.organization_id == tenant.organization_id,
            Version.quote_id == quote.id,
            Version.version == quote.current_version,
        )
    )
    return QuoteState(
        id=quote.id,
        number=quote.number,
        contact_id=quote.contact_id,
        status=quote.status.value,
        version=quote.current_version,
        version_approved=version is not None and version.status is VersionStatus.APPROVED,
        valid_until=version.valid_until if version is not None else None,
    )
