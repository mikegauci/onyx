"""Stock-match alerts (VA-005 part 1): wanted criteria on leads, matches, and staff-sent alerts.

- Staff save what a lead's buyer wants. A confirmed, active record is matched against every
  available car; new or changed cars from an import are matched against every such record.
  Matching is ``matching.match``: deterministic, with the reasons stored on the match.
- A match is unique per contact and car, so a buyer is offered a car at most once.
- Nothing is sent automatically. Staff send matches (one or several at once). Each send checks
  again, in its own savepoint: the car is still available and still matches, the contact has an
  active ``car_alerts`` consent, and they have a WhatsApp thread on the alert template's
  channel. The approved **marketing** template then goes out once (idempotency key
  ``car-alert-{match id}``). Anything that fails is reported per match; nothing else changes.
"""

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator
from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit.record import record_workspace_audit
from app.core.auth.deps import WorkspaceAccess
from app.core.errors import (
    AppError,
    ConflictError,
    ErrorDetail,
    NotFoundError,
    ValidationFailedError,
)
from app.core.modules.access import module_enabled
from app.core.modules.registry import ModuleKey
from app.modules.automotive import matching
from app.modules.automotive.models import (
    AlertSettings,
    Match,
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

MAX_SEND = 50
PARAM_KEYS = ("first_name", "vehicle", "price", "link")
Text100 = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
Text64 = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=64)]


# --- schemas ---------------------------------------------------------------------------------


class _Input(BaseModel):
    model_config = ConfigDict(extra="forbid")


class WantedIn(_Input):
    make: Text100 | None = None
    model: Text100 | None = None
    price_max_cents: int | None = Field(default=None, gt=0, le=100_000_000)
    year_min: int | None = Field(default=None, ge=1900, le=2100)
    mileage_max_km: int | None = Field(default=None, ge=0, le=2_000_000)
    fuel: Text64 | None = None

    @model_validator(mode="after")
    def _some(self) -> "WantedIn":
        if not matching.has_criteria(self):
            raise ValueError("Give at least one criterion.")
        return self


class WantedUpdate(WantedIn):
    active: bool = True


class WantedOut(BaseModel):
    id: uuid.UUID
    lead_id: uuid.UUID
    contact_id: uuid.UUID
    make: str | None
    model: str | None
    price_max_cents: int | None
    year_min: int | None
    mileage_max_km: int | None
    fuel: str | None
    active: bool
    source: WantedSource
    confirmed: bool
    pending_matches: int
    created_at: datetime
    updated_at: datetime


class WantedList(BaseModel):
    items: list[WantedOut]


class MatchVehicle(BaseModel):
    id: uuid.UUID
    title: str
    status: VehicleStatus
    price_cents: int | None
    listing_url: str | None
    photo: str | None


class MatchContact(BaseModel):
    id: uuid.UUID
    full_name: str
    has_phone: bool
    consented: bool


class MatchOut(BaseModel):
    id: uuid.UUID
    status: MatchStatus
    reasons: list[str]
    skip_reason: str | None
    wanted_id: uuid.UUID
    lead_id: uuid.UUID
    contact: MatchContact
    vehicle: MatchVehicle
    created_at: datetime
    decided_at: datetime | None


class MatchList(BaseModel):
    items: list[MatchOut]
    total: int


class SendRequest(_Input):
    match_ids: list[uuid.UUID] = Field(min_length=1, max_length=MAX_SEND)


class SendSkip(BaseModel):
    match_id: uuid.UUID
    reason: str
    message: str


class SendResult(BaseModel):
    sent: list[uuid.UUID]
    skipped: list[SendSkip]


class AlertSettingsIn(_Input):
    template_id: uuid.UUID | None = Field(
        description="An approved WhatsApp marketing template; null turns alerts off"
    )
    params: list[str] = Field(
        default_factory=list,
        max_length=20,
        description=f"What fills each template value, in order: {', '.join(PARAM_KEYS)}",
    )


class AlertSettingsOut(BaseModel):
    template_id: uuid.UUID | None
    template_name: str | None
    template_body: str | None
    params: list[str]
    param_keys: list[str]
    ready: bool = Field(description="A usable marketing template is chosen")


# --- the service -----------------------------------------------------------------------------

SKIP_TEXT = {
    "car_not_available": "The car is no longer available.",
    "no_longer_matches": "The buyer's criteria no longer match this car.",
    "no_consent": "The customer has not agreed to car alerts.",
    "no_phone": "The customer has no phone number.",
    "no_whatsapp_conversation": "The customer has never written on the alerts WhatsApp number.",
    "not_set_up": "Choose the alerts template in Settings first.",
    "already_decided": "This match was already sent or dismissed.",
}


def _skip(match_id: uuid.UUID, reason: str, message: str | None = None) -> SendSkip:
    return SendSkip(match_id=match_id, reason=reason, message=message or SKIP_TEXT[reason])


def _first_name(full_name: str) -> str:
    return full_name.split()[0] if full_name.split() else "there"


class AlertService:
    def __init__(self, db: AsyncSession, workspace: WorkspaceAccess) -> None:
        self.db = db
        self.workspace = workspace
        self.tenant = workspace.tenant
        self.org = workspace.tenant.organization_id

    async def _audit(
        self, action: str, target_type: str, target_id: uuid.UUID, **details: Any
    ) -> None:
        await record_workspace_audit(
            self.db,
            self.workspace,
            action=f"automotive.{action}",
            target_type=target_type,
            target_id=target_id,
            details=details,
        )

    # --- wanted ----------------------------------------------------------------------------

    async def _wanted(self, wanted_id: uuid.UUID, *, lock: bool = False) -> Wanted:
        query = select(Wanted).where(Wanted.organization_id == self.org, Wanted.id == wanted_id)
        row = await self.db.scalar(query.with_for_update() if lock else query)
        if row is None:
            raise NotFoundError("Wanted criteria not found.")
        return row

    async def _wanted_out(self, rows: Sequence[Wanted]) -> list[WantedOut]:
        ids = [w.id for w in rows]
        counts: dict[uuid.UUID, int] = {}
        if ids:
            counts = dict(
                (
                    await self.db.execute(
                        select(Match.wanted_id, func.count())
                        .where(
                            Match.organization_id == self.org,
                            Match.wanted_id.in_(ids),
                            Match.status == MatchStatus.PENDING.value,
                        )
                        .group_by(Match.wanted_id)
                    )
                ).all()
            )
        return [
            WantedOut(
                id=w.id,
                lead_id=w.lead_id,
                contact_id=w.contact_id,
                make=w.make,
                model=w.model,
                price_max_cents=w.price_max_cents,
                year_min=w.year_min,
                mileage_max_km=w.mileage_max_km,
                fuel=w.fuel,
                active=w.active,
                source=WantedSource(w.source),
                confirmed=w.confirmed_at is not None,
                pending_matches=counts.get(w.id, 0),
                created_at=w.created_at,
                updated_at=w.updated_at,
            )
            for w in rows
        ]

    async def list_wanted(self, lead_id: uuid.UUID) -> WantedList:
        await self._lead(lead_id)
        rows = (
            await self.db.scalars(
                select(Wanted)
                .where(Wanted.organization_id == self.org, Wanted.lead_id == lead_id)
                .order_by(Wanted.created_at)
            )
        ).all()
        return WantedList(items=await self._wanted_out(rows))

    async def _lead(self, lead_id: uuid.UUID) -> crm.LeadSummary:
        lead = await crm.get_lead(self.db, self.tenant, lead_id)
        if lead is None:
            raise NotFoundError("Lead not found.")
        return lead

    async def create_wanted(
        self, lead_id: uuid.UUID, body: WantedIn, *, source: WantedSource = WantedSource.STAFF
    ) -> WantedOut:
        lead = await self._lead(lead_id)
        if lead.archived:
            raise ConflictError("Restore the lead before adding what the buyer wants.")
        now = datetime.now(UTC)
        staff = source is WantedSource.STAFF
        wanted = Wanted(
            organization_id=self.org,
            lead_id=lead.id,
            contact_id=lead.contact_id,
            source=source.value,
            confirmed_at=now if staff else None,
            confirmed_by_user_id=self.workspace.user.id if staff else None,
            created_by_user_id=self.workspace.user.id if staff else None,
            **body.model_dump(),
        )
        self.db.add(wanted)
        await self.db.flush()
        await self._audit("wanted.created", "automotive_wanted", wanted.id, source=source.value)
        await self.refresh_for_wanted(wanted)
        return (await self._wanted_out([wanted]))[0]

    async def update_wanted(self, wanted_id: uuid.UUID, body: WantedUpdate) -> WantedOut:
        wanted = await self._wanted(wanted_id, lock=True)
        for name, value in body.model_dump(exclude={"active"}).items():
            setattr(wanted, name, value)
        wanted.active = body.active
        wanted.updated_at = datetime.now(UTC)
        if wanted.confirmed_at is None:  # editing a suggestion confirms it
            wanted.confirmed_at = wanted.updated_at
            wanted.confirmed_by_user_id = self.workspace.user.id
        await self.db.flush()
        await self._audit("wanted.updated", "automotive_wanted", wanted.id, active=body.active)
        await self._close_stale(wanted)
        await self.refresh_for_wanted(wanted)
        return (await self._wanted_out([wanted]))[0]

    async def confirm_wanted(self, wanted_id: uuid.UUID) -> WantedOut:
        wanted = await self._wanted(wanted_id, lock=True)
        if wanted.confirmed_at is None:
            wanted.confirmed_at = datetime.now(UTC)
            wanted.confirmed_by_user_id = self.workspace.user.id
            await self.db.flush()
            await self._audit("wanted.confirmed", "automotive_wanted", wanted.id)
            await self.refresh_for_wanted(wanted)
        return (await self._wanted_out([wanted]))[0]

    async def _close_stale(self, wanted: Wanted) -> None:
        """Pending matches of a record that changed: drop those that no longer match."""
        pending = (
            await self.db.scalars(
                select(Match).where(
                    Match.organization_id == self.org,
                    Match.wanted_id == wanted.id,
                    Match.status == MatchStatus.PENDING.value,
                )
            )
        ).all()
        if not pending:
            return
        cars = await self._vehicles([m.vehicle_id for m in pending])
        now = datetime.now(UTC)
        for m in pending:
            car = cars.get(m.vehicle_id)
            if not wanted.active or car is None or not matching.match(wanted, car).ok:
                m.status = MatchStatus.SKIPPED.value
                m.skip_reason = "no_longer_matches"
                m.updated_at = now
        await self.db.flush()

    # --- matching --------------------------------------------------------------------------

    async def _vehicles(self, ids: Sequence[uuid.UUID]) -> dict[uuid.UUID, Vehicle]:
        if not ids:
            return {}
        rows = await self.db.scalars(
            select(Vehicle).where(Vehicle.organization_id == self.org, Vehicle.id.in_(set(ids)))
        )
        return {v.id: v for v in rows.all()}

    async def _insert(self, pairs: list[tuple[Wanted, Vehicle, list[str]]]) -> int:
        added = 0
        for wanted, car, reasons in pairs:
            row = await self.db.scalar(
                insert(Match)
                .values(
                    organization_id=self.org,
                    wanted_id=wanted.id,
                    contact_id=wanted.contact_id,
                    vehicle_id=car.id,
                    status=MatchStatus.PENDING.value,
                    reasons=reasons,
                )
                .on_conflict_do_nothing(constraint="uq_automotive_matches_contact_car")
                .returning(Match.id)
            )
            added += row is not None
        return added

    async def refresh_for_wanted(self, wanted: Wanted) -> int:
        if not wanted.active or wanted.confirmed_at is None:
            return 0
        cars = (
            await self.db.scalars(
                select(Vehicle).where(
                    Vehicle.organization_id == self.org,
                    Vehicle.status == VehicleStatus.AVAILABLE.value,
                    Vehicle.held_by_deal_id.is_(None),
                )
            )
        ).all()
        pairs = []
        for car in cars:
            result = matching.match(wanted, car)
            if result.ok:
                pairs.append((wanted, car, result.reasons))
        return await self._insert(pairs)

    async def refresh_for_vehicles(self, vehicle_ids: Sequence[uuid.UUID]) -> int:
        """After an import: match new or changed available cars against every active record."""
        cars = [
            c
            for c in (await self._vehicles(vehicle_ids)).values()
            if c.status == VehicleStatus.AVAILABLE.value and c.held_by_deal_id is None
        ]
        if not cars:
            return 0
        wanted = (
            await self.db.scalars(
                select(Wanted).where(
                    Wanted.organization_id == self.org,
                    Wanted.active.is_(True),
                    Wanted.confirmed_at.is_not(None),
                )
            )
        ).all()
        pairs = []
        for w in wanted:
            for car in cars:
                result = matching.match(w, car)
                if result.ok:
                    pairs.append((w, car, result.reasons))
        return await self._insert(pairs)

    # --- listing and deciding --------------------------------------------------------------

    async def list_matches(
        self,
        *,
        status: MatchStatus | None,
        vehicle_id: uuid.UUID | None,
        lead_id: uuid.UUID | None,
        limit: int,
        offset: int,
    ) -> MatchList:
        conditions = [Match.organization_id == self.org]
        if status is not None:
            conditions.append(Match.status == status.value)
        if vehicle_id is not None:
            conditions.append(Match.vehicle_id == vehicle_id)
        if lead_id is not None:
            conditions.append(
                Match.wanted_id.in_(
                    select(Wanted.id).where(
                        Wanted.organization_id == self.org, Wanted.lead_id == lead_id
                    )
                )
            )
        total = await self.db.scalar(select(func.count()).select_from(Match).where(*conditions))
        rows = (
            await self.db.scalars(
                select(Match)
                .where(*conditions)
                .order_by(Match.created_at.desc(), Match.id)
                .limit(limit)
                .offset(offset)
            )
        ).all()
        return MatchList(items=await self._match_out(rows), total=total or 0)

    async def _match_out(self, rows: Sequence[Match]) -> list[MatchOut]:
        cars = await self._vehicles([m.vehicle_id for m in rows])
        contacts = await crm.get_contacts(self.db, self.tenant, {m.contact_id for m in rows})
        agreed = await consented(
            self.db, self.tenant, [m.contact_id for m in rows], ConsentPurpose.CAR_ALERTS
        )
        leads = {
            w.id: w.lead_id
            for w in (
                await self.db.scalars(
                    select(Wanted).where(
                        Wanted.organization_id == self.org,
                        Wanted.id.in_({m.wanted_id for m in rows} or {uuid.uuid4()}),
                    )
                )
            ).all()
        }
        out = []
        for m in rows:
            car = cars[m.vehicle_id]
            contact = contacts.get(m.contact_id)
            out.append(
                MatchOut(
                    id=m.id,
                    status=MatchStatus(m.status),
                    reasons=list(m.reasons),
                    skip_reason=m.skip_reason,
                    wanted_id=m.wanted_id,
                    lead_id=leads[m.wanted_id],
                    contact=MatchContact(
                        id=m.contact_id,
                        full_name=contact.full_name if contact else "Unknown contact",
                        has_phone=bool(contact and contact.phone),
                        consented=m.contact_id in agreed,
                    ),
                    vehicle=MatchVehicle(
                        id=car.id,
                        title=car.title,
                        status=VehicleStatus(car.status),
                        price_cents=car.price_cents,
                        listing_url=car.listing_url,
                        photo=car.photos[0] if car.photos else None,
                    ),
                    created_at=m.created_at,
                    decided_at=m.decided_at,
                )
            )
        return out

    async def _match(self, match_id: uuid.UUID) -> Match:
        row = await self.db.scalar(
            select(Match)
            .where(Match.organization_id == self.org, Match.id == match_id)
            .with_for_update()
        )
        if row is None:
            raise NotFoundError("Match not found.")
        return row

    async def dismiss(self, match_id: uuid.UUID) -> MatchOut:
        match = await self._match(match_id)
        if match.status == MatchStatus.SENT.value:
            raise ConflictError("This alert was already sent.")
        if match.status != MatchStatus.DISMISSED.value:
            match.status = MatchStatus.DISMISSED.value
            match.skip_reason = None
            match.decided_by_user_id = self.workspace.user.id
            match.decided_at = datetime.now(UTC)
            await self.db.flush()
            await self._audit("match.dismissed", "automotive_match", match.id)
        return (await self._match_out([match]))[0]

    # --- settings --------------------------------------------------------------------------

    async def _settings_row(self) -> AlertSettings | None:
        return await self.db.scalar(
            select(AlertSettings).where(AlertSettings.organization_id == self.org)
        )

    async def settings(self) -> AlertSettingsOut:
        row = await self._settings_row()
        template = (
            await inbox.whatsapp_template(self.db, self.tenant, row.template_id)
            if row is not None and row.template_id is not None
            else None
        )
        params = list(row.params) if row is not None else []
        return AlertSettingsOut(
            template_id=template.id if template else None,
            template_name=template.name if template else None,
            template_body=template.body if template else None,
            params=params,
            param_keys=list(PARAM_KEYS),
            ready=bool(
                template and template.usable_for_marketing and len(params) == template.param_count
            ),
        )

    async def update_settings(self, body: AlertSettingsIn) -> AlertSettingsOut:
        if body.template_id is not None:
            template = await inbox.whatsapp_template(self.db, self.tenant, body.template_id)
            if template is None or not template.usable_for_marketing:
                raise ValidationFailedError(
                    "Choose an approved, supported WhatsApp marketing template.",
                    details=[
                        ErrorDetail(loc=["body", "template_id"], msg="not usable", type="template")
                    ],
                )
            if len(body.params) != template.param_count or any(
                p not in PARAM_KEYS for p in body.params
            ):
                raise ValidationFailedError(
                    f"The template has {template.param_count} values; fill each with one of "
                    f"{', '.join(PARAM_KEYS)}.",
                    details=[ErrorDetail(loc=["body", "params"], msg="mismatch", type="params")],
                )
        row = await self._settings_row()
        if row is None:
            row = AlertSettings(organization_id=self.org)
            self.db.add(row)
        row.template_id = body.template_id
        row.params = list(body.params) if body.template_id else []
        row.updated_by_user_id = self.workspace.user.id
        row.updated_at = datetime.now(UTC)
        await self.db.flush()
        await self._audit(
            "alerts.settings_updated",
            "automotive_alert_settings",
            self.org,
            template_id=str(body.template_id) if body.template_id else None,
        )
        return await self.settings()

    # --- sending ---------------------------------------------------------------------------

    def _values(self, keys: Sequence[str], full_name: str, car: Vehicle) -> list[str]:
        values = {
            "first_name": _first_name(full_name),
            "vehicle": car.title,
            "price": matching.euros(car.price_cents)
            if car.price_cents is not None
            else "on request",
            "link": car.listing_url or car.title,
        }
        return [values[k] for k in keys]

    async def send(self, body: SendRequest) -> SendResult:
        row = await self._settings_row()
        config = await self.settings()
        if not config.ready or row is None or row.template_id is None:
            raise ConflictError(SKIP_TEXT["not_set_up"])
        if not await module_enabled(self.db, self.workspace, ModuleKey.INBOX):
            raise ConflictError("Car alerts need the inbox module.")
        template = await inbox.whatsapp_template(self.db, self.tenant, row.template_id)
        assert template is not None  # noqa: S101 - ready implies it
        sent: list[uuid.UUID] = []
        skipped: list[SendSkip] = []
        for match_id in dict.fromkeys(body.match_ids):  # in order, without repeats
            outcome = await self._send_one(match_id, template, list(row.params))
            if isinstance(outcome, SendSkip):
                skipped.append(outcome)
            else:
                sent.append(outcome)
        return SendResult(sent=sent, skipped=skipped)

    async def _mark_skipped(self, match: Match, reason: str) -> None:
        match.status = MatchStatus.SKIPPED.value
        match.skip_reason = reason
        match.updated_at = datetime.now(UTC)
        await self.db.flush()

    async def _send_one(
        self, match_id: uuid.UUID, template: inbox.TemplateInfo, keys: list[str]
    ) -> uuid.UUID | SendSkip:
        match = await self.db.scalar(
            select(Match)
            .where(Match.organization_id == self.org, Match.id == match_id)
            .with_for_update()
        )
        if match is None:
            return _skip(match_id, "not_found", "Match not found.")
        if match.status not in (MatchStatus.PENDING.value, MatchStatus.SKIPPED.value):
            return _skip(match_id, "already_decided")
        car = (await self._vehicles([match.vehicle_id]))[match.vehicle_id]
        wanted = await self._wanted(match.wanted_id)
        reason: str | None = None
        if car.status != VehicleStatus.AVAILABLE.value or car.held_by_deal_id is not None:
            reason = "car_not_available"
        elif not wanted.active or wanted.confirmed_at is None or not matching.match(wanted, car).ok:
            reason = "no_longer_matches"
        elif not await consented(
            self.db, self.tenant, [match.contact_id], ConsentPurpose.CAR_ALERTS
        ):
            reason = "no_consent"
        contact = (await crm.get_contacts(self.db, self.tenant, [match.contact_id])).get(
            match.contact_id
        )
        if reason is None and (contact is None or not contact.phone):
            reason = "no_phone"
        if reason is not None:
            await self._mark_skipped(match, reason)
            return _skip(match.id, reason)
        assert contact is not None  # noqa: S101 - checked above
        try:
            async with self.db.begin_nested():
                conversation_id = await inbox.whatsapp_conversation_for_contact(
                    self.db, self.workspace, match.contact_id, template.channel_id
                )
                if conversation_id is None:
                    raise _NoThreadError
                rendered = await inbox.render_template(
                    self.db,
                    self.workspace,
                    conversation_id,
                    template.id,
                    self._values(keys, contact.full_name, car),
                    marketing=True,
                )
                reply = await inbox.send_reply(
                    self.db,
                    self.workspace,
                    conversation_id,
                    rendered.body,
                    idempotency_key=f"car-alert-{match.id}",
                    template=rendered,
                )
        except _NoThreadError:
            await self._mark_skipped(match, "no_whatsapp_conversation")
            return _skip(match.id, "no_whatsapp_conversation")
        except (ConflictError, ValidationFailedError, NotFoundError) as exc:
            await self._mark_skipped(match, "cannot_send")
            return _skip(match.id, "cannot_send", exc.message)
        except AppError as exc:  # the provider failed or did not answer: try again later
            return _skip(match.id, "send_failed", exc.message)
        match.status = MatchStatus.SENT.value
        match.skip_reason = None
        match.message_id = reply.message_id
        match.decided_by_user_id = self.workspace.user.id
        match.decided_at = datetime.now(UTC)
        match.updated_at = match.decided_at
        await self.db.flush()
        await self._audit(
            "alert.sent",
            "automotive_match",
            match.id,
            vehicle_id=str(match.vehicle_id),
            message_id=str(reply.message_id),
        )
        return match.id


class _NoThreadError(Exception):
    pass


async def deactivate_pending(
    db: AsyncSession, org: uuid.UUID, vehicle_ids: Sequence[uuid.UUID]
) -> None:
    """Cars that left stock: their pending matches can no longer be sent."""
    if not vehicle_ids:
        return
    await db.execute(
        update(Match)
        .where(
            Match.organization_id == org,
            Match.vehicle_id.in_(set(vehicle_ids)),
            Match.status == MatchStatus.PENDING.value,
        )
        .values(
            status=MatchStatus.SKIPPED.value, skip_reason="car_not_available", updated_at=func.now()
        )
    )
