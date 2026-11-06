"""The quotations module's public interface for other modules (the sales assistant, PR-015).

``draft_quote`` creates a **draft** quote through the normal service, so numbering, price
snapshots, VAT and totals are computed exactly as for staff-made quotes. Drafts are never sent
and must be approved by staff (PR-016).
"""

import uuid
from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth.deps import WorkspaceAccess
from app.core.db.context import TenantContext
from app.modules.quotations import schemas
from app.modules.quotations.models import Quote
from app.modules.quotations.service import QuotationService


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
