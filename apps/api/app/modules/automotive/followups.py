"""Interest and sold-car follow-up (VA-005 part 2).

- **Interest:** a contact asked about a car. It is recorded when the assistant found the car for
  the contact's conversation (``record_interest``), or when staff link a car to a lead.
- **Follow-up:** when a car becomes ``sold`` (website import or a deal), everyone who asked
  about it in the last 30 days gets one follow-up row. The buyer is excluded, and so is anyone
  with a deal on that car. Each row carries up to 3 similar available cars (``matching.similar``).
  A contact with no similar car gets no row.
- **Sending:** staff send, nothing is automatic. Inside WhatsApp's 24-hour window the reply is
  free-form text listing the cars. Outside it, it needs the customer's ``car_alerts`` consent
  and goes as the car-alert marketing template with the closest car. Each follow-up is sent
  once (key ``sold-followup-{id}``).
- **Suggestions:** the assistant's suggested criteria are stored unconfirmed
  (``suggest_wanted``) and match nothing until staff confirm them.
"""

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit.record import record_workspace_audit
from app.core.auth.deps import WorkspaceAccess
from app.core.db.context import TenantContext
from app.core.errors import AppError, ConflictError, NotFoundError, ValidationFailedError
from app.modules.automotive import matching
from app.modules.automotive.alerts import AlertService, SendSkip, WantedIn, _first_name
from app.modules.automotive.models import (
    Followup,
    Interest,
    InterestSource,
    MatchStatus,
    Vehicle,
    VehicleStatus,
    Wanted,
    WantedSource,
)
from app.modules.crm import public as crm
from app.modules.crm.consents import consented
from app.modules.crm.models import ConsentPurpose
from app.modules.inbox import public as inbox

INTEREST_WINDOW = timedelta(days=30)
TEXT_MAX = 1000


# --- interest --------------------------------------------------------------------------------


async def record_interest(
    db: AsyncSession,
    tenant: TenantContext,
    *,
    contact_id: uuid.UUID,
    vehicle_ids: Sequence[uuid.UUID],
    conversation_id: uuid.UUID | None,
    source: InterestSource,
) -> None:
    """Note that the contact asked about these cars (now). Repeats only move ``last_at``."""
    now = datetime.now(UTC)
    for vehicle_id in dict.fromkeys(vehicle_ids):
        statement = insert(Interest).values(
            organization_id=tenant.organization_id,
            contact_id=contact_id,
            vehicle_id=vehicle_id,
            conversation_id=conversation_id,
            source=source.value,
            last_at=now,
        )
        await db.execute(
            statement.on_conflict_do_update(
                constraint="uq_automotive_interests_contact_car",
                set_={
                    "last_at": now,
                    "conversation_id": statement.excluded.conversation_id,
                },
            )
        )


async def suggest_wanted(
    db: AsyncSession, workspace: WorkspaceAccess, lead_id: uuid.UUID, criteria: dict[str, Any]
) -> bool:
    """Store the assistant's suggested criteria for a lead, unconfirmed. True if stored.

    An open (unconfirmed) suggestion on the lead is replaced instead of adding another.
    """
    try:
        body = WantedIn.model_validate(criteria)
    except ValueError:
        return False
    lead = await crm.get_lead(db, workspace.tenant, lead_id)
    if lead is None or lead.archived:
        return False
    org = workspace.tenant.organization_id
    open_suggestion = await db.scalar(
        select(Wanted)
        .where(
            Wanted.organization_id == org,
            Wanted.lead_id == lead_id,
            Wanted.source == WantedSource.ASSISTANT.value,
            Wanted.confirmed_at.is_(None),
        )
        .with_for_update()
    )
    if open_suggestion is not None:
        for name, value in body.model_dump().items():
            setattr(open_suggestion, name, value)
        open_suggestion.updated_at = datetime.now(UTC)
        await db.flush()
        return True
    db.add(
        Wanted(
            organization_id=org,
            lead_id=lead.id,
            contact_id=lead.contact_id,
            source=WantedSource.ASSISTANT.value,
            **body.model_dump(),
        )
    )
    await db.flush()
    return True


# --- follow-ups when a car is sold -----------------------------------------------------------


async def _available(db: AsyncSession, org: uuid.UUID) -> list[Vehicle]:
    return list(
        (
            await db.scalars(
                select(Vehicle).where(
                    Vehicle.organization_id == org,
                    Vehicle.status == VehicleStatus.AVAILABLE.value,
                    Vehicle.held_by_deal_id.is_(None),
                )
            )
        ).all()
    )


async def on_sold(db: AsyncSession, tenant: TenantContext, vehicle_ids: Sequence[uuid.UUID]) -> int:
    """Create the follow-ups for cars that just became sold. Returns how many were created."""
    org = tenant.organization_id
    sold = (
        await db.scalars(
            select(Vehicle).where(
                Vehicle.organization_id == org,
                Vehicle.id.in_(set(vehicle_ids)),
                Vehicle.status == VehicleStatus.SOLD.value,
            )
        )
    ).all()
    if not sold:
        return 0
    stock = await _available(db, org)
    since = datetime.now(UTC) - INTEREST_WINDOW
    created = 0
    for car in sold:
        suggestions = [str(c.id) for c in matching.similar(car, stock)]
        if not suggestions:
            continue
        # The buyer, and anyone with a deal on this car, are not offered other cars.
        dealt = set(
            (
                await db.execute(
                    text(
                        "SELECT contact_id FROM deals WHERE organization_id = :org "
                        "AND vehicle_id = :car"
                    ),
                    {"org": org, "car": car.id},
                )
            )
            .scalars()
            .all()
        )
        interested = (
            await db.scalars(
                select(Interest).where(
                    Interest.organization_id == org,
                    Interest.vehicle_id == car.id,
                    Interest.last_at >= since,
                )
            )
        ).all()
        for interest in interested:
            if interest.contact_id in dealt:
                continue
            row = await db.scalar(
                insert(Followup)
                .values(
                    organization_id=org,
                    contact_id=interest.contact_id,
                    sold_vehicle_id=car.id,
                    conversation_id=interest.conversation_id,
                    suggestions=suggestions,
                    status=MatchStatus.PENDING.value,
                )
                .on_conflict_do_nothing(constraint="uq_automotive_followups_contact_car")
                .returning(Followup.id)
            )
            created += row is not None
    return created


# --- staff API -------------------------------------------------------------------------------


class InterestIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    vehicle_id: uuid.UUID


class SuggestedCar(BaseModel):
    id: uuid.UUID
    title: str
    status: VehicleStatus
    price_cents: int | None
    listing_url: str | None


class FollowupOut(BaseModel):
    id: uuid.UUID
    status: MatchStatus
    skip_reason: str | None
    contact_id: uuid.UUID
    contact_name: str
    consented: bool
    sold_vehicle: SuggestedCar
    suggestions: list[SuggestedCar]
    created_at: datetime
    decided_at: datetime | None


class FollowupList(BaseModel):
    items: list[FollowupOut]
    total: int


class FollowupSendRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    followup_ids: list[uuid.UUID] = Field(min_length=1, max_length=50)


class FollowupSendResult(BaseModel):
    sent: list[uuid.UUID]
    skipped: list[SendSkip]


FOLLOWUP_SKIP = {
    "no_suggestions": "None of the similar cars is still available.",
    "no_consent": (
        "More than 24 hours since the customer last wrote, and they have not agreed to car alerts."
    ),
    "not_set_up": "Outside the 24-hour window this needs the car-alert template (Settings).",
    "no_whatsapp_conversation": "The customer has no WhatsApp conversation to reply in.",
    "already_decided": "This follow-up was already sent or dismissed.",
}


def _skip(followup_id: uuid.UUID, reason: str, message: str | None = None) -> SendSkip:
    return SendSkip(match_id=followup_id, reason=reason, message=message or FOLLOWUP_SKIP[reason])


def follow_up_text(first_name: str, sold_title: str, cars: Sequence[Vehicle]) -> str:
    """The free-form reply inside the 24-hour window. Prices and links come from stock."""
    lines = [
        f"Hi {first_name}, the {sold_title} you asked about has now been sold. "
        "Similar cars we have available:"
    ]
    for car in cars:
        price = (
            matching.euros(car.price_cents) if car.price_cents is not None else "price on request"
        )
        lines.append(
            f"- {car.title}, {price}" + (f": {car.listing_url}" if car.listing_url else "")
        )
    lines.append("Reply here if you would like to see one.")
    return "\n".join(lines)[:TEXT_MAX]


class FollowupService:
    def __init__(self, db: AsyncSession, workspace: WorkspaceAccess) -> None:
        self.db = db
        self.workspace = workspace
        self.tenant = workspace.tenant
        self.org = workspace.tenant.organization_id

    async def link(self, lead_id: uuid.UUID, body: InterestIn) -> None:
        lead = await crm.get_lead(self.db, self.tenant, lead_id)
        if lead is None:
            raise NotFoundError("Lead not found.")
        car = await self.db.scalar(
            select(Vehicle.id).where(
                Vehicle.organization_id == self.org, Vehicle.id == body.vehicle_id
            )
        )
        if car is None:
            raise ValidationFailedError("Vehicle not found.")
        await record_interest(
            self.db,
            self.tenant,
            contact_id=lead.contact_id,
            vehicle_ids=[body.vehicle_id],
            conversation_id=None,
            source=InterestSource.STAFF,
        )

    async def _cars(self, ids: set[uuid.UUID]) -> dict[uuid.UUID, Vehicle]:
        if not ids:
            return {}
        rows = await self.db.scalars(
            select(Vehicle).where(Vehicle.organization_id == self.org, Vehicle.id.in_(ids))
        )
        return {v.id: v for v in rows.all()}

    async def _out(self, rows: Sequence[Followup]) -> list[FollowupOut]:
        ids = {r.sold_vehicle_id for r in rows} | {
            uuid.UUID(s) for r in rows for s in r.suggestions
        }
        cars = await self._cars(ids)
        contacts = await crm.get_contacts(self.db, self.tenant, {r.contact_id for r in rows})
        agreed = await consented(
            self.db, self.tenant, [r.contact_id for r in rows], ConsentPurpose.CAR_ALERTS
        )

        def car_out(car: Vehicle) -> SuggestedCar:
            return SuggestedCar(
                id=car.id,
                title=car.title,
                status=VehicleStatus(car.status),
                price_cents=car.price_cents,
                listing_url=car.listing_url,
            )

        return [
            FollowupOut(
                id=r.id,
                status=MatchStatus(r.status),
                skip_reason=r.skip_reason,
                contact_id=r.contact_id,
                contact_name=(c.full_name if (c := contacts.get(r.contact_id)) else "Unknown"),
                consented=r.contact_id in agreed,
                sold_vehicle=car_out(cars[r.sold_vehicle_id]),
                suggestions=[
                    car_out(cars[uuid.UUID(s)]) for s in r.suggestions if uuid.UUID(s) in cars
                ],
                created_at=r.created_at,
                decided_at=r.decided_at,
            )
            for r in rows
        ]

    async def list(self, status: MatchStatus | None, limit: int, offset: int) -> FollowupList:
        conditions = [Followup.organization_id == self.org]
        if status is not None:
            conditions.append(Followup.status == status.value)
        total = await self.db.scalar(select(func.count()).select_from(Followup).where(*conditions))
        rows = (
            await self.db.scalars(
                select(Followup)
                .where(*conditions)
                .order_by(Followup.created_at.desc(), Followup.id)
                .limit(limit)
                .offset(offset)
            )
        ).all()
        return FollowupList(items=await self._out(rows), total=total or 0)

    async def _row(self, followup_id: uuid.UUID) -> Followup | None:
        return await self.db.scalar(
            select(Followup)
            .where(Followup.organization_id == self.org, Followup.id == followup_id)
            .with_for_update()
        )

    async def dismiss(self, followup_id: uuid.UUID) -> FollowupOut:
        row = await self._row(followup_id)
        if row is None:
            raise NotFoundError("Follow-up not found.")
        if row.status == MatchStatus.SENT.value:
            raise ConflictError("This follow-up was already sent.")
        row.status = MatchStatus.DISMISSED.value
        row.skip_reason = None
        row.decided_by_user_id = self.workspace.user.id
        row.decided_at = datetime.now(UTC)
        await self.db.flush()
        await record_workspace_audit(
            self.db,
            self.workspace,
            action="automotive.followup.dismissed",
            target_type="automotive_followup",
            target_id=row.id,
        )
        return (await self._out([row]))[0]

    async def send(self, body: FollowupSendRequest) -> FollowupSendResult:
        sent: list[uuid.UUID] = []
        skipped: list[SendSkip] = []
        alerts = AlertService(self.db, self.workspace)
        for followup_id in dict.fromkeys(body.followup_ids):
            outcome = await self._send_one(followup_id, alerts)
            if isinstance(outcome, SendSkip):
                skipped.append(outcome)
            else:
                sent.append(outcome)
        return FollowupSendResult(sent=sent, skipped=skipped)

    async def _mark_skipped(self, row: Followup, reason: str) -> SendSkip:
        row.status = MatchStatus.SKIPPED.value
        row.skip_reason = reason
        row.updated_at = datetime.now(UTC)
        await self.db.flush()
        return _skip(row.id, reason)

    async def _conversation(self, row: Followup, channel_id: uuid.UUID | None) -> uuid.UUID | None:
        """The enquiry's own WhatsApp thread if known, else the contact's latest one on the
        alert template's channel (any WhatsApp channel when no template is chosen)."""
        if row.conversation_id is not None:
            thread = await inbox.get_thread(self.db, self.tenant, row.conversation_id, limit=1)
            if thread is not None and await inbox.is_whatsapp(
                self.db, self.tenant, thread.conversation_id
            ):
                return await inbox.reopen_for_reply(self.db, self.workspace, thread.conversation_id)
        return await inbox.whatsapp_conversation_for_contact(
            self.db, self.workspace, row.contact_id, channel_id
        )

    async def _send_one(self, followup_id: uuid.UUID, alerts: AlertService) -> uuid.UUID | SendSkip:
        row = await self._row(followup_id)
        if row is None:
            return _skip(followup_id, "not_found", "Follow-up not found.")
        if row.status not in (MatchStatus.PENDING.value, MatchStatus.SKIPPED.value):
            return _skip(row.id, "already_decided")
        cars = await self._cars({uuid.UUID(s) for s in row.suggestions} | {row.sold_vehicle_id})
        sold = cars[row.sold_vehicle_id]
        still = [
            cars[uuid.UUID(s)]
            for s in row.suggestions
            if uuid.UUID(s) in cars
            and cars[uuid.UUID(s)].status == VehicleStatus.AVAILABLE.value
            and cars[uuid.UUID(s)].held_by_deal_id is None
        ]
        if not still:
            return await self._mark_skipped(row, "no_suggestions")
        contact = (await crm.get_contacts(self.db, self.tenant, [row.contact_id])).get(
            row.contact_id
        )
        if contact is None or not contact.phone:
            return await self._mark_skipped(row, "no_whatsapp_conversation")
        settings = await alerts.settings()
        template = (
            await inbox.whatsapp_template(self.db, self.tenant, settings.template_id)
            if settings.ready and settings.template_id is not None
            else None
        )
        key = f"sold-followup-{row.id}"
        try:
            async with self.db.begin_nested():
                conversation_id = await self._conversation(
                    row, template.channel_id if template else None
                )
                if conversation_id is None:
                    raise _SkipError("no_whatsapp_conversation")
                if await inbox.whatsapp_window_open(self.db, self.workspace, conversation_id):
                    body = follow_up_text(_first_name(contact.full_name), sold.title, still)
                    reply = await inbox.send_reply(
                        self.db, self.workspace, conversation_id, body, idempotency_key=key
                    )
                else:
                    if template is None:
                        raise _SkipError("not_set_up")
                    if not await consented(
                        self.db, self.tenant, [row.contact_id], ConsentPurpose.CAR_ALERTS
                    ):
                        raise _SkipError("no_consent")
                    rendered = await inbox.render_template(
                        self.db,
                        self.workspace,
                        conversation_id,
                        template.id,
                        alerts._values(settings.params, contact.full_name, still[0]),
                        marketing=True,
                    )
                    reply = await inbox.send_reply(
                        self.db,
                        self.workspace,
                        conversation_id,
                        rendered.body,
                        idempotency_key=key,
                        template=rendered,
                    )
        except _SkipError as skip:
            return await self._mark_skipped(row, skip.reason)
        except (ConflictError, ValidationFailedError, NotFoundError) as exc:
            await self._mark_skipped(row, "cannot_send")
            return _skip(row.id, "cannot_send", exc.message)
        except AppError as exc:
            return _skip(row.id, "send_failed", exc.message)
        row.status = MatchStatus.SENT.value
        row.skip_reason = None
        row.message_id = reply.message_id
        row.decided_by_user_id = self.workspace.user.id
        row.decided_at = datetime.now(UTC)
        row.updated_at = row.decided_at
        await self.db.flush()
        await record_workspace_audit(
            self.db,
            self.workspace,
            action="automotive.followup.sent",
            target_type="automotive_followup",
            target_id=row.id,
            details={"sold_vehicle_id": str(row.sold_vehicle_id), "cars": len(still)},
        )
        return row.id


class _SkipError(Exception):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason
