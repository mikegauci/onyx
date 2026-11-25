"""Marketing consent on contacts (VA-005): staff record it, staff or a WhatsApp STOP withdraw it.

Only an active (recorded and not withdrawn) consent lets another module send a marketing
message. Granting and withdrawing are audited and noted in the contact's activity stream.
A STOP comes in through the WhatsApp webhook (no acting user); the withdrawn row itself records
it (``withdrawn_via = whatsapp_stop``).
"""

import uuid
from collections.abc import Iterable
from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth.deps import WorkspaceAccess
from app.core.db.context import TenantContext
from app.core.errors import ConflictError
from app.core.tenancy.models import User
from app.modules.crm.models import (
    ActivityKind,
    ConsentMethod,
    ConsentPurpose,
    ConsentWithdrawnVia,
    MarketingConsent,
    SubjectType,
)
from app.modules.crm.service import CrmService


class ConsentGrant(BaseModel):
    model_config = ConfigDict(extra="forbid")

    method: ConsentMethod = Field(description="How the customer agreed")
    note: str | None = Field(default=None, max_length=300)
    granted_at: datetime | None = Field(
        default=None, description="When they agreed; now when omitted. Never in the future."
    )


class ConsentEntry(BaseModel):
    id: uuid.UUID
    method: ConsentMethod
    note: str | None
    granted_at: datetime
    recorded_by: str | None
    withdrawn_at: datetime | None
    withdrawn_via: ConsentWithdrawnVia | None


class ConsentOut(BaseModel):
    purpose: ConsentPurpose
    active: bool
    history: list[ConsentEntry] = Field(description="Newest first")


class ConsentService:
    def __init__(self, db: AsyncSession, workspace: WorkspaceAccess) -> None:
        self.db = db
        self.workspace = workspace
        self.org = workspace.tenant.organization_id
        self.crm = CrmService(db, workspace)

    async def read(self, contact_id: uuid.UUID, purpose: ConsentPurpose) -> ConsentOut:
        await self.crm.get_contact(contact_id)
        rows = (
            await self.db.execute(
                select(MarketingConsent, User.display_name)
                .outerjoin(User, User.id == MarketingConsent.recorded_by_user_id)
                .where(
                    MarketingConsent.organization_id == self.org,
                    MarketingConsent.contact_id == contact_id,
                    MarketingConsent.purpose == purpose.value,
                )
                .order_by(MarketingConsent.granted_at.desc(), MarketingConsent.created_at.desc())
            )
        ).all()
        history = [
            ConsentEntry(
                id=row.id,
                method=ConsentMethod(row.method),
                note=row.note,
                granted_at=row.granted_at,
                recorded_by=name,
                withdrawn_at=row.withdrawn_at,
                withdrawn_via=ConsentWithdrawnVia(row.withdrawn_via) if row.withdrawn_via else None,
            )
            for row, name in rows
        ]
        return ConsentOut(
            purpose=purpose,
            active=any(h.withdrawn_at is None for h in history),
            history=history,
        )

    async def grant(
        self, contact_id: uuid.UUID, purpose: ConsentPurpose, body: ConsentGrant
    ) -> ConsentOut:
        contact = await self.crm.get_contact(contact_id)
        if contact.erased_at is not None or contact.archived_at is not None:
            raise ConflictError("Restore the contact before recording consent.")
        now = datetime.now(UTC)
        granted = body.granted_at or now
        if granted.tzinfo is None or granted > now:
            raise ConflictError("The consent date must be a past date with a time zone.")
        active = await _active(self.db, self.org, contact_id, purpose)
        if active is not None:
            raise ConflictError("This contact's consent is already recorded.")
        row = MarketingConsent(
            organization_id=self.org,
            contact_id=contact_id,
            purpose=purpose.value,
            method=body.method.value,
            note=body.note.strip() if body.note and body.note.strip() else None,
            granted_at=granted,
            recorded_by_user_id=self.workspace.user.id,
        )
        self.db.add(row)
        await self.db.flush()
        details = {"purpose": purpose.value, "method": body.method.value, "consent": "granted"}
        self.crm._activity(SubjectType.CONTACT, contact_id, ActivityKind.UPDATED, details=details)
        await self.crm._audit("crm.consent.granted", "contact", contact_id, details)
        return await self.read(contact_id, purpose)

    async def withdraw(self, contact_id: uuid.UUID, purpose: ConsentPurpose) -> ConsentOut:
        await self.crm.get_contact(contact_id)
        active = await _active(self.db, self.org, contact_id, purpose)
        if active is None:
            raise ConflictError("This contact has no consent to withdraw.")
        active.withdrawn_at = datetime.now(UTC)
        active.withdrawn_via = ConsentWithdrawnVia.STAFF.value
        active.withdrawn_by_user_id = self.workspace.user.id
        await self.db.flush()
        details = {"purpose": purpose.value, "consent": "withdrawn"}
        self.crm._activity(SubjectType.CONTACT, contact_id, ActivityKind.UPDATED, details=details)
        await self.crm._audit("crm.consent.withdrawn", "contact", contact_id, details)
        return await self.read(contact_id, purpose)


async def _active(
    db: AsyncSession, org: uuid.UUID, contact_id: uuid.UUID, purpose: ConsentPurpose
) -> MarketingConsent | None:
    return await db.scalar(
        select(MarketingConsent)
        .where(
            MarketingConsent.organization_id == org,
            MarketingConsent.contact_id == contact_id,
            MarketingConsent.purpose == purpose.value,
            MarketingConsent.withdrawn_at.is_(None),
        )
        .with_for_update()
    )


# --- for other modules ---------------------------------------------------------------------


async def consented(
    db: AsyncSession,
    tenant: TenantContext,
    contact_ids: Iterable[uuid.UUID],
    purpose: ConsentPurpose,
) -> set[uuid.UUID]:
    """The contacts among ``contact_ids`` with an active consent for ``purpose``."""
    ids = list(set(contact_ids))
    if not ids:
        return set()
    rows = await db.scalars(
        select(MarketingConsent.contact_id).where(
            MarketingConsent.organization_id == tenant.organization_id,
            MarketingConsent.contact_id.in_(ids),
            MarketingConsent.purpose == purpose.value,
            MarketingConsent.withdrawn_at.is_(None),
        )
    )
    return set(rows.all())


async def withdraw_all_on_stop(
    db: AsyncSession, tenant: TenantContext, contact_id: uuid.UUID
) -> int:
    """A WhatsApp STOP from this contact: withdraw every active marketing consent."""
    result = await db.execute(
        update(MarketingConsent)
        .where(
            MarketingConsent.organization_id == tenant.organization_id,
            MarketingConsent.contact_id == contact_id,
            MarketingConsent.withdrawn_at.is_(None),
        )
        .values(withdrawn_at=datetime.now(UTC), withdrawn_via=ConsentWithdrawnVia.WHATSAPP_STOP)
    )
    return int(getattr(result, "rowcount", 0) or 0)
