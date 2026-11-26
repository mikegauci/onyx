"""Customer cars and renewal/service reminders (VA-009 part 2).

- A customer car is added when a deal is collected (one per deal) or by staff. It holds the
  licence and insurance due dates (each with "the dealer handles it"), the last service and
  the service interval (12 months by default), and a pause switch.
- Due dates (``due_dates``, pure): licence and insurance only when the dealer handles them;
  service one interval after the last service, or after collection when there is none.
- The scheduler (``create_due``) adds a pending reminder when today is inside a kind's window
  (``days`` before the due date, up to ``GRACE`` after it). Unique per car, kind and due date,
  so one reminder per due date however often it runs. Paused cars get none.
- Nothing sends automatically. Staff send reminders: WhatsApp first (free-form inside 24h,
  else that kind's approved utility template), then email. Opted-out addresses are refused.
- Moving a due date (a renewal or a recorded service) dismisses the pending reminder for the
  old date.
"""

import calendar
import uuid
from collections.abc import Sequence
from datetime import UTC, date, datetime, timedelta
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator
from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit.record import record_workspace_audit
from app.core.auth.deps import WorkspaceAccess
from app.core.db.context import TenantContext
from app.core.errors import (
    AppError,
    ConflictError,
    ErrorDetail,
    NotFoundError,
    ValidationFailedError,
)
from app.modules.automotive.models import (
    CustomerCar,
    Reminder,
    ReminderKind,
    ReminderSettings,
    Vehicle,
)
from app.modules.crm import public as crm
from app.modules.inbox import public as inbox

MAX_SEND = 50
GRACE = timedelta(days=30)  # an overdue date still gets a reminder for this long
KINDS = (ReminderKind.LICENCE, ReminderKind.INSURANCE, ReminderKind.SERVICE)
DEFAULT_DAYS = {ReminderKind.LICENCE: 30, ReminderKind.INSURANCE: 30, ReminderKind.SERVICE: 14}
PARAM_KEYS = ("first_name", "vehicle", "registration", "due_date")
DEFAULT_MESSAGE = {
    ReminderKind.LICENCE: (
        "Hi {name}, the road licence for your {car} ({registration}) is due on {due}. "
        "Reply here and we will renew it for you."
    ),
    ReminderKind.INSURANCE: (
        "Hi {name}, the insurance for your {car} ({registration}) is due on {due}. "
        "Reply here and we will arrange the renewal."
    ),
    ReminderKind.SERVICE: (
        "Hi {name}, your {car} ({registration}) is due for its service on {due}. "
        "Reply here to book it in."
    ),
}
SUBJECT = {
    ReminderKind.LICENCE: "Your {car}: road licence due {due}",
    ReminderKind.INSURANCE: "Your {car}: insurance due {due}",
    ReminderKind.SERVICE: "Your {car}: service due {due}",
}
Text200 = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
Text1000 = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)]
Registration = Annotated[
    str, StringConstraints(strip_whitespace=True, to_upper=True, min_length=1, max_length=16)
]


# --- pure rules ------------------------------------------------------------------------------


def add_months(day: date, months: int) -> date:
    """``day`` moved by whole months; the 31st becomes the month's last day."""
    total = day.month - 1 + months
    year, month = day.year + total // 12, total % 12 + 1
    return date(year, month, min(day.day, calendar.monthrange(year, month)[1]))


def due_dates(
    *,
    licence_due_on: date | None,
    dealer_handles_licence: bool,
    insurance_due_on: date | None,
    dealer_handles_insurance: bool,
    last_service_on: date | None,
    collected_on: date | None,
    service_interval_months: int,
) -> dict[ReminderKind, date | None]:
    service_from = last_service_on or collected_on
    return {
        ReminderKind.LICENCE: licence_due_on if dealer_handles_licence else None,
        ReminderKind.INSURANCE: insurance_due_on if dealer_handles_insurance else None,
        ReminderKind.SERVICE: add_months(service_from, service_interval_months)
        if service_from is not None
        else None,
    }


def car_due_dates(car: CustomerCar) -> dict[ReminderKind, date | None]:
    return due_dates(
        licence_due_on=car.licence_due_on,
        dealer_handles_licence=car.dealer_handles_licence,
        insurance_due_on=car.insurance_due_on,
        dealer_handles_insurance=car.dealer_handles_insurance,
        last_service_on=car.last_service_on,
        collected_on=car.collected_on,
        service_interval_months=car.service_interval_months,
    )


def in_window(due: date, today: date, days: int) -> bool:
    """From ``days`` before the due date until ``GRACE`` after it."""
    return due - timedelta(days=days) <= today <= due + GRACE


def format_day(day: date) -> str:
    return day.strftime("%d/%m/%Y")


def render(template: str, *, name: str, car: str, registration: str | None, due: date) -> str:
    out = template if registration else template.replace(" ({registration})", "")
    for key, value in (
        ("name", name),
        ("car", car),
        ("registration", registration or ""),
        ("due", format_day(due)),
    ):
        out = out.replace("{" + key + "}", value)
    return out


def _first_name(full_name: str) -> str:
    parts = full_name.split()
    return parts[0] if parts else "there"


# --- schemas ---------------------------------------------------------------------------------


class _Input(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CustomerCarUpdate(_Input):
    description: Text200
    registration: Registration | None = None
    collected_on: date | None = None
    licence_due_on: date | None = None
    dealer_handles_licence: bool = False
    insurance_due_on: date | None = None
    dealer_handles_insurance: bool = False
    last_service_on: date | None = None
    service_interval_months: int = Field(default=12, ge=1, le=60)
    reminders_paused: bool = False


class CustomerCarIn(CustomerCarUpdate):
    contact_id: uuid.UUID
    vehicle_id: uuid.UUID | None = None


class ServiceRecord(_Input):
    serviced_on: date

    @field_validator("serviced_on")
    @classmethod
    def _past(cls, value: date) -> date:
        if value > datetime.now(UTC).date() + timedelta(days=1):
            raise ValueError("The service date cannot be in the future.")
        return value


class CustomerCarOut(BaseModel):
    id: uuid.UUID
    contact_id: uuid.UUID
    vehicle_id: uuid.UUID | None
    deal_id: uuid.UUID | None
    description: str
    registration: str | None
    collected_on: date | None
    licence_due_on: date | None
    dealer_handles_licence: bool
    insurance_due_on: date | None
    dealer_handles_insurance: bool
    last_service_on: date | None
    service_interval_months: int
    reminders_paused: bool
    next_licence_on: date | None
    next_insurance_on: date | None
    next_service_on: date | None
    created_at: datetime


class CustomerCarList(BaseModel):
    items: list[CustomerCarOut]


class ReminderOut(BaseModel):
    id: uuid.UUID
    kind: ReminderKind
    due_on: date
    status: str = Field(description="pending, sent, dismissed or skipped")
    channel: str | None
    skip_reason: str | None
    customer_car_id: uuid.UUID
    car: str
    registration: str | None
    contact_id: uuid.UUID
    contact_name: str
    has_phone: bool
    has_email: bool
    created_at: datetime
    decided_at: datetime | None


class ReminderList(BaseModel):
    items: list[ReminderOut]
    total: int


class ReminderSendRequest(_Input):
    reminder_ids: list[uuid.UUID] = Field(min_length=1, max_length=MAX_SEND)


class ReminderSkip(BaseModel):
    reminder_id: uuid.UUID
    reason: str
    message: str


class ReminderSendResult(BaseModel):
    sent: list[uuid.UUID]
    skipped: list[ReminderSkip]


class KindSettingsIn(_Input):
    days: int = Field(ge=1, le=90, description="Days before the due date it is listed")
    message: Text1000 | None = Field(
        default=None,
        description="Email and free-form WhatsApp: {name}, {car}, {registration}, {due}",
    )
    template_id: uuid.UUID | None = Field(
        default=None, description="An approved WhatsApp utility template, used outside 24h"
    )
    params: list[str] = Field(
        default_factory=list,
        max_length=10,
        description=f"What fills each template value, in order: {', '.join(PARAM_KEYS)}",
    )


class ReminderSettingsIn(_Input):
    licence: KindSettingsIn
    insurance: KindSettingsIn
    service: KindSettingsIn


class KindSettingsOut(BaseModel):
    days: int
    message: str
    template_id: uuid.UUID | None
    template_name: str | None
    template_body: str | None
    params: list[str]
    template_ready: bool


class ReminderSettingsOut(BaseModel):
    licence: KindSettingsOut
    insurance: KindSettingsOut
    service: KindSettingsOut
    param_keys: list[str]


SKIP_TEXT = {
    "not_found": "Reminder not found.",
    "already_decided": "This reminder was already sent or dismissed.",
    "paused": "Reminders are paused for this car.",
    "no_longer_due": "The due date has changed since this reminder was created.",
    "no_channel": "The customer has no WhatsApp conversation or email address to send to.",
    "cannot_send": "The message could not be sent.",
    "send_failed": "The provider did not accept the message. Try again later.",
}


def _skip(reminder_id: uuid.UUID, reason: str, message: str | None = None) -> ReminderSkip:
    return ReminderSkip(
        reminder_id=reminder_id, reason=reason, message=message or SKIP_TEXT[reason]
    )


def _car_out(car: CustomerCar) -> CustomerCarOut:
    due = car_due_dates(car)
    return CustomerCarOut(
        id=car.id,
        contact_id=car.contact_id,
        vehicle_id=car.vehicle_id,
        deal_id=car.deal_id,
        description=car.description,
        registration=car.registration,
        collected_on=car.collected_on,
        licence_due_on=car.licence_due_on,
        dealer_handles_licence=car.dealer_handles_licence,
        insurance_due_on=car.insurance_due_on,
        dealer_handles_insurance=car.dealer_handles_insurance,
        last_service_on=car.last_service_on,
        service_interval_months=car.service_interval_months,
        reminders_paused=car.reminders_paused,
        next_licence_on=due[ReminderKind.LICENCE],
        next_insurance_on=due[ReminderKind.INSURANCE],
        next_service_on=due[ReminderKind.SERVICE],
        created_at=car.created_at,
    )


# --- scheduler -------------------------------------------------------------------------------


def _days(settings: ReminderSettings | None, kind: ReminderKind) -> int:
    value = getattr(settings, f"{kind.value}_days", None) if settings is not None else None
    return int(value) if value is not None else DEFAULT_DAYS[kind]


async def create_due(db: AsyncSession, tenant: TenantContext, today: date) -> int:
    """Add the pending reminders now inside their window. Idempotent; runs as the worker."""
    org = tenant.organization_id
    settings = await db.scalar(
        select(ReminderSettings).where(ReminderSettings.organization_id == org)
    )
    cars = (
        await db.scalars(
            select(CustomerCar).where(
                CustomerCar.organization_id == org, CustomerCar.reminders_paused.is_(False)
            )
        )
    ).all()
    rows = []
    for car in cars:
        for kind, due in car_due_dates(car).items():
            if due is not None and in_window(due, today, _days(settings, kind)):
                rows.append(
                    {
                        "organization_id": org,
                        "customer_car_id": car.id,
                        "contact_id": car.contact_id,
                        "kind": kind.value,
                        "due_on": due,
                        "status": "pending",
                    }
                )
    if not rows:
        return 0
    result = await db.execute(
        insert(Reminder)
        .values(rows)
        .on_conflict_do_nothing(constraint="uq_automotive_reminders_car_kind_due")
        .returning(Reminder.id)
    )
    return len(result.scalars().all())


# --- adding a car from a deal (called by the deals module) ------------------------------------


async def add_from_deal(
    db: AsyncSession,
    workspace: WorkspaceAccess,
    *,
    contact_id: uuid.UUID,
    vehicle_id: uuid.UUID | None,
    deal_id: uuid.UUID,
    description: str,
    collected_on: date,
) -> None:
    """The collected car joins the customer's cars, once per deal."""
    if vehicle_id is not None:
        title = await db.scalar(
            select(Vehicle.title).where(
                Vehicle.organization_id == workspace.tenant.organization_id,
                Vehicle.id == vehicle_id,
            )
        )
        description = title or description
    await db.execute(
        insert(CustomerCar)
        .values(
            organization_id=workspace.tenant.organization_id,
            contact_id=contact_id,
            vehicle_id=vehicle_id,
            deal_id=deal_id,
            description=description[:200],
            collected_on=collected_on,
            created_by_user_id=workspace.user.id,
        )
        .on_conflict_do_nothing(
            index_elements=["organization_id", "deal_id"],
            index_where=CustomerCar.deal_id.is_not(None),
        )
    )


# --- the service -----------------------------------------------------------------------------


class ReminderService:
    def __init__(self, db: AsyncSession, workspace: WorkspaceAccess) -> None:
        self.db = db
        self.workspace = workspace
        self.tenant = workspace.tenant
        self.org = workspace.tenant.organization_id

    async def _audit(
        self, action: str, target_type: str, target_id: uuid.UUID, **details: object
    ) -> None:
        await record_workspace_audit(
            self.db,
            self.workspace,
            action=action,
            target_type=target_type,
            target_id=target_id,
            details=details or None,
        )

    # --- customer cars ---------------------------------------------------------------------

    async def list_cars(self, contact_id: uuid.UUID) -> CustomerCarList:
        rows = (
            await self.db.scalars(
                select(CustomerCar)
                .where(
                    CustomerCar.organization_id == self.org, CustomerCar.contact_id == contact_id
                )
                .order_by(CustomerCar.created_at.desc(), CustomerCar.id)
            )
        ).all()
        return CustomerCarList(items=[_car_out(c) for c in rows])

    async def _car(self, car_id: uuid.UUID) -> CustomerCar:
        car = await self.db.scalar(
            select(CustomerCar)
            .where(CustomerCar.organization_id == self.org, CustomerCar.id == car_id)
            .with_for_update()
        )
        if car is None:
            raise NotFoundError("Car not found.")
        return car

    async def create_car(self, body: CustomerCarIn) -> CustomerCarOut:
        contact = (await crm.get_contacts(self.db, self.tenant, [body.contact_id])).get(
            body.contact_id
        )
        if contact is None:
            raise ValidationFailedError(
                "Contact not found.",
                details=[ErrorDetail(loc=["body", "contact_id"], msg="not found", type="missing")],
            )
        if body.vehicle_id is not None:
            found = await self.db.scalar(
                select(Vehicle.id).where(
                    Vehicle.organization_id == self.org, Vehicle.id == body.vehicle_id
                )
            )
            if found is None:
                raise ValidationFailedError(
                    "Vehicle not found.",
                    details=[
                        ErrorDetail(loc=["body", "vehicle_id"], msg="not found", type="missing")
                    ],
                )
        car = CustomerCar(
            organization_id=self.org,
            contact_id=body.contact_id,
            vehicle_id=body.vehicle_id,
            created_by_user_id=self.workspace.user.id,
            **body.model_dump(exclude={"contact_id", "vehicle_id"}),
        )
        self.db.add(car)
        await self.db.flush()
        await self._audit("automotive.customer_car.created", "automotive_customer_car", car.id)
        return _car_out(car)

    async def update_car(self, car_id: uuid.UUID, body: CustomerCarUpdate) -> CustomerCarOut:
        car = await self._car(car_id)
        for key, value in body.model_dump().items():
            setattr(car, key, value)
        car.updated_at = datetime.now(UTC)
        await self.db.flush()
        await self._close_stale(car)
        await self._audit("automotive.customer_car.updated", "automotive_customer_car", car.id)
        return _car_out(car)

    async def record_service(self, car_id: uuid.UUID, body: ServiceRecord) -> CustomerCarOut:
        car = await self._car(car_id)
        car.last_service_on = body.serviced_on
        car.updated_at = datetime.now(UTC)
        await self.db.flush()
        await self._close_stale(car)
        await self._audit(
            "automotive.customer_car.serviced",
            "automotive_customer_car",
            car.id,
            serviced_on=body.serviced_on.isoformat(),
        )
        return _car_out(car)

    async def _close_stale(self, car: CustomerCar) -> None:
        """Pending reminders whose date no longer applies (or the car is paused) are dismissed."""
        now = datetime.now(UTC)
        for kind, due in car_due_dates(car).items():
            conditions = [
                Reminder.organization_id == self.org,
                Reminder.customer_car_id == car.id,
                Reminder.kind == kind.value,
                Reminder.status.in_(("pending", "skipped")),
            ]
            if due is not None and not car.reminders_paused:
                conditions.append(Reminder.due_on != due)
            await self.db.execute(
                update(Reminder)
                .where(*conditions)
                .values(
                    status="dismissed",
                    skip_reason=None,
                    decided_by_user_id=self.workspace.user.id,
                    decided_at=now,
                    updated_at=now,
                )
            )

    # --- reminders -------------------------------------------------------------------------

    async def _out(self, rows: Sequence[Reminder]) -> list[ReminderOut]:
        if not rows:
            return []
        cars = {
            c.id: c
            for c in (
                await self.db.scalars(
                    select(CustomerCar).where(
                        CustomerCar.organization_id == self.org,
                        CustomerCar.id.in_({r.customer_car_id for r in rows}),
                    )
                )
            ).all()
        }
        contacts = await crm.get_contacts(self.db, self.tenant, {r.contact_id for r in rows})
        out = []
        for r in rows:
            car = cars.get(r.customer_car_id)
            contact = contacts.get(r.contact_id)
            out.append(
                ReminderOut(
                    id=r.id,
                    kind=ReminderKind(r.kind),
                    due_on=r.due_on,
                    status=r.status,
                    channel=r.channel,
                    skip_reason=r.skip_reason,
                    customer_car_id=r.customer_car_id,
                    car=car.description if car else "Car",
                    registration=car.registration if car else None,
                    contact_id=r.contact_id,
                    contact_name=contact.full_name if contact else "Unknown",
                    has_phone=bool(contact and contact.phone),
                    has_email=bool(contact and contact.email),
                    created_at=r.created_at,
                    decided_at=r.decided_at,
                )
            )
        return out

    async def list(
        self, status: str | None, kind: ReminderKind | None, limit: int, offset: int
    ) -> ReminderList:
        conditions = [Reminder.organization_id == self.org]
        if status is not None:
            conditions.append(Reminder.status == status)
        if kind is not None:
            conditions.append(Reminder.kind == kind.value)
        total = await self.db.scalar(select(func.count()).select_from(Reminder).where(*conditions))
        rows = (
            await self.db.scalars(
                select(Reminder)
                .where(*conditions)
                .order_by(Reminder.due_on, Reminder.id)
                .limit(limit)
                .offset(offset)
            )
        ).all()
        return ReminderList(items=await self._out(rows), total=total or 0)

    async def _row(self, reminder_id: uuid.UUID) -> Reminder | None:
        return await self.db.scalar(
            select(Reminder)
            .where(Reminder.organization_id == self.org, Reminder.id == reminder_id)
            .with_for_update()
        )

    async def dismiss(self, reminder_id: uuid.UUID) -> ReminderOut:
        row = await self._row(reminder_id)
        if row is None:
            raise NotFoundError("Reminder not found.")
        if row.status == "sent":
            raise ConflictError("This reminder was already sent.")
        row.status = "dismissed"
        row.skip_reason = None
        row.decided_by_user_id = self.workspace.user.id
        row.decided_at = datetime.now(UTC)
        row.updated_at = row.decided_at
        await self.db.flush()
        await self._audit("automotive.reminder.dismissed", "automotive_reminder", row.id)
        return (await self._out([row]))[0]

    # --- settings --------------------------------------------------------------------------

    async def _settings_row(self) -> ReminderSettings | None:
        return await self.db.scalar(
            select(ReminderSettings).where(ReminderSettings.organization_id == self.org)
        )

    async def _kind_out(self, row: ReminderSettings | None, kind: ReminderKind) -> KindSettingsOut:
        k = kind.value
        template_id = getattr(row, f"{k}_template_id", None) if row else None
        template = (
            await inbox.whatsapp_template(self.db, self.tenant, template_id)
            if template_id is not None
            else None
        )
        params = list(getattr(row, f"{k}_params", []) or []) if row else []
        message = getattr(row, f"{k}_message", None) if row else None
        return KindSettingsOut(
            days=_days(row, kind),
            message=message or DEFAULT_MESSAGE[kind],
            template_id=template.id if template else None,
            template_name=template.name if template else None,
            template_body=template.body if template else None,
            params=params,
            template_ready=bool(
                template and template.usable_for_utility and len(params) == template.param_count
            ),
        )

    async def settings(self) -> ReminderSettingsOut:
        row = await self._settings_row()
        return ReminderSettingsOut(
            licence=await self._kind_out(row, ReminderKind.LICENCE),
            insurance=await self._kind_out(row, ReminderKind.INSURANCE),
            service=await self._kind_out(row, ReminderKind.SERVICE),
            param_keys=list(PARAM_KEYS),
        )

    async def update_settings(self, body: ReminderSettingsIn) -> ReminderSettingsOut:
        for kind in KINDS:
            part: KindSettingsIn = getattr(body, kind.value)
            if part.template_id is None:
                continue
            template = await inbox.whatsapp_template(self.db, self.tenant, part.template_id)
            if template is None or not template.usable_for_utility:
                raise ValidationFailedError(
                    "Choose an approved, supported WhatsApp utility template.",
                    details=[
                        ErrorDetail(
                            loc=["body", kind.value, "template_id"],
                            msg="not usable",
                            type="template",
                        )
                    ],
                )
            if len(part.params) != template.param_count or any(
                p not in PARAM_KEYS for p in part.params
            ):
                raise ValidationFailedError(
                    f"The template has {template.param_count} values; fill each with one of "
                    f"{', '.join(PARAM_KEYS)}.",
                    details=[
                        ErrorDetail(
                            loc=["body", kind.value, "params"], msg="mismatch", type="params"
                        )
                    ],
                )
        row = await self._settings_row()
        if row is None:
            row = ReminderSettings(organization_id=self.org)
            self.db.add(row)
        for kind in KINDS:
            part = getattr(body, kind.value)
            setattr(row, f"{kind.value}_days", part.days)
            setattr(row, f"{kind.value}_message", part.message)
            setattr(row, f"{kind.value}_template_id", part.template_id)
            setattr(row, f"{kind.value}_params", list(part.params) if part.template_id else [])
        row.updated_by_user_id = self.workspace.user.id
        row.updated_at = datetime.now(UTC)
        await self.db.flush()
        await self._audit(
            "automotive.reminder_settings.updated", "automotive_reminder_settings", self.org
        )
        return await self.settings()

    # --- sending ---------------------------------------------------------------------------

    async def send(self, body: ReminderSendRequest) -> ReminderSendResult:
        settings = await self.settings()
        sent: list[uuid.UUID] = []
        skipped: list[ReminderSkip] = []
        for reminder_id in dict.fromkeys(body.reminder_ids):
            outcome = await self._send_one(reminder_id, settings)
            if isinstance(outcome, ReminderSkip):
                skipped.append(outcome)
            else:
                sent.append(outcome)
        return ReminderSendResult(sent=sent, skipped=skipped)

    async def _mark_skipped(self, row: Reminder, reason: str) -> None:
        row.status = "skipped"
        row.skip_reason = reason
        row.updated_at = datetime.now(UTC)
        await self.db.flush()

    async def _send_one(
        self, reminder_id: uuid.UUID, settings: ReminderSettingsOut
    ) -> uuid.UUID | ReminderSkip:
        row = await self._row(reminder_id)
        if row is None:
            return _skip(reminder_id, "not_found")
        if row.status not in ("pending", "skipped"):
            return _skip(row.id, "already_decided")
        kind = ReminderKind(row.kind)
        car = await self.db.scalar(
            select(CustomerCar).where(
                CustomerCar.organization_id == self.org, CustomerCar.id == row.customer_car_id
            )
        )
        if car is None or car.reminders_paused:
            await self._mark_skipped(row, "paused")
            return _skip(row.id, "paused")
        if car_due_dates(car)[kind] != row.due_on:
            await self._mark_skipped(row, "no_longer_due")
            return _skip(row.id, "no_longer_due")
        contact = (await crm.get_contacts(self.db, self.tenant, [row.contact_id])).get(
            row.contact_id
        )
        if contact is None:
            await self._mark_skipped(row, "no_channel")
            return _skip(row.id, "no_channel")
        config: KindSettingsOut = getattr(settings, kind.value)
        name = _first_name(contact.full_name)
        text_body = render(
            config.message,
            name=name,
            car=car.description,
            registration=car.registration,
            due=row.due_on,
        )
        subject = render(
            SUBJECT[kind],
            name=name,
            car=car.description,
            registration=car.registration,
            due=row.due_on,
        )
        template = (
            await inbox.whatsapp_template(self.db, self.tenant, config.template_id)
            if config.template_ready and config.template_id is not None
            else None
        )
        values = {
            "first_name": name,
            "vehicle": car.description,
            "registration": car.registration or car.description,
            "due_date": format_day(row.due_on),
        }
        try:
            async with self.db.begin_nested():
                delivered = await inbox.deliver_to_contact(
                    self.db,
                    self.workspace,
                    contact,
                    text=text_body,
                    email_subject=subject,
                    idempotency_key=f"reminder-{row.id}",
                    template=inbox.TemplateChoice(
                        template.id, template.channel_id, [values[k] for k in config.params]
                    )
                    if template is not None
                    else None,
                )
        except inbox.NoChannelError:
            await self._mark_skipped(row, "no_channel")
            return _skip(row.id, "no_channel")
        except (ConflictError, ValidationFailedError, NotFoundError) as exc:
            await self._mark_skipped(row, "cannot_send")
            return _skip(row.id, "cannot_send", exc.message)
        except AppError as exc:
            return _skip(row.id, "send_failed", exc.message)
        row.status = "sent"
        row.channel = delivered.channel
        row.skip_reason = None
        row.message_id = delivered.message_id
        row.decided_by_user_id = self.workspace.user.id
        row.decided_at = datetime.now(UTC)
        row.updated_at = row.decided_at
        await self.db.flush()
        await self._audit(
            "automotive.reminder.sent",
            "automotive_reminder",
            row.id,
            kind=row.kind,
            channel=delivered.channel,
        )
        return row.id
