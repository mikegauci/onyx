"""Payment reminders (VA-008 part 2).

- The scheduler (``create_due``) adds a pending reminder for each unpaid installment of an
  active, unpaused schedule: ``before_due`` a few days before the due date and ``overdue`` a
  few days after it (``schedule_rules.reminders_due``). One per installment and kind.
- Nothing sends automatically. Staff send reminders: WhatsApp first (free-form inside 24h, else
  that kind's approved utility template), then email. Each send checks again that the
  installment is still unpaid and the schedule active and unpaused.
- Pausing or cancelling a schedule dismisses its pending reminders.
"""

import uuid
from collections.abc import Sequence
from datetime import UTC, date, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints
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
from app.modules.crm import public as crm
from app.modules.deals.models import (
    FinanceInstallment,
    FinancePayment,
    FinanceReminder,
    FinanceReminderSettings,
    FinanceSchedule,
)
from app.modules.deals.schedule_rules import InstallmentState, allocate, reminders_due
from app.modules.inbox import public as inbox

MAX_SEND = 50
Kind = Literal["before_due", "overdue"]
KINDS: tuple[Kind, ...] = ("before_due", "overdue")
SETTING = {"before_due": "before", "overdue": "overdue"}  # column prefix per kind
DEFAULT_DAYS = {"before_due": 3, "overdue": 3}
PARAM_KEYS = ("first_name", "vehicle", "amount", "due_date")
DEFAULT_MESSAGE = {
    "before_due": (
        "Hi {name}, a reminder that your payment of {amount} for your {car} is due on {due}. "
        "Reply here if you have any questions."
    ),
    "overdue": (
        "Hi {name}, our records show your payment of {amount} for your {car}, due on {due}, "
        "has not been received yet. If you have already paid, please ignore this message, "
        "otherwise reply here and we will help."
    ),
}
SUBJECT = {
    "before_due": "Payment reminder: {amount} due {due}",
    "overdue": "Payment overdue: {amount} due {due}",
}
Text1000 = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)]


def euros(cents: int) -> str:
    whole, part = divmod(abs(cents), 100)
    return f"{'-' if cents < 0 else ''}€{whole:,}.{part:02d}"


def format_day(day: date) -> str:
    return day.strftime("%d/%m/%Y")


def render(template: str, *, name: str, car: str, amount: int, due: date) -> str:
    out = template
    for key, value in (
        ("name", name),
        ("car", car),
        ("amount", euros(amount)),
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


class KindSettingsIn(_Input):
    days: int = Field(
        ge=1, le=60, description="Days before (before_due, max 30) or after (overdue)"
    )
    message: Text1000 | None = Field(
        default=None, description="Email and free-form WhatsApp: {name}, {car}, {amount}, {due}"
    )
    template_id: uuid.UUID | None = None
    params: list[str] = Field(
        default_factory=list,
        max_length=10,
        description=f"What fills each template value, in order: {', '.join(PARAM_KEYS)}",
    )


class PaymentReminderSettingsIn(_Input):
    before_due: KindSettingsIn
    overdue: KindSettingsIn


class KindSettingsOut(BaseModel):
    days: int
    message: str
    template_id: uuid.UUID | None
    template_name: str | None
    template_body: str | None
    params: list[str]
    template_ready: bool


class PaymentReminderSettingsOut(BaseModel):
    before_due: KindSettingsOut
    overdue: KindSettingsOut
    param_keys: list[str]


class PaymentReminderOut(BaseModel):
    id: uuid.UUID
    kind: Kind
    due_on: date
    status: str = Field(description="pending, sent, dismissed or skipped")
    channel: str | None
    skip_reason: str | None
    schedule_id: uuid.UUID
    label: str
    installment_number: int
    owed_cents: int = Field(description="What is still unpaid on the installment now")
    contact_id: uuid.UUID
    contact_name: str
    has_phone: bool
    has_email: bool
    created_at: datetime
    decided_at: datetime | None


class PaymentReminderList(BaseModel):
    items: list[PaymentReminderOut]
    total: int


class PaymentReminderSendRequest(_Input):
    reminder_ids: list[uuid.UUID] = Field(min_length=1, max_length=MAX_SEND)


class PaymentReminderSkip(BaseModel):
    reminder_id: uuid.UUID
    reason: str
    message: str


class PaymentReminderSendResult(BaseModel):
    sent: list[uuid.UUID]
    skipped: list[PaymentReminderSkip]


SKIP_TEXT = {
    "not_found": "Reminder not found.",
    "already_decided": "This reminder was already sent or dismissed.",
    "paid": "The installment has been paid since.",
    "paused": "Reminders are paused, or the schedule is no longer active.",
    "no_channel": "The customer has no WhatsApp conversation or email address to send to.",
    "cannot_send": "The message could not be sent.",
    "send_failed": "The provider did not accept the message. Try again later.",
}


def _skip(reminder_id: uuid.UUID, reason: str, message: str | None = None) -> PaymentReminderSkip:
    return PaymentReminderSkip(
        reminder_id=reminder_id, reason=reason, message=message or SKIP_TEXT[reason]
    )


# --- owed amounts ------------------------------------------------------------------------------


async def _owed(
    db: AsyncSession, org: uuid.UUID, schedule_ids: Sequence[uuid.UUID], today: date
) -> dict[uuid.UUID, tuple[int, InstallmentState]]:
    """Per installment id: what is unpaid and its state, payments applied oldest first."""
    if not schedule_ids:
        return {}
    installments = (
        await db.scalars(
            select(FinanceInstallment).where(
                FinanceInstallment.organization_id == org,
                FinanceInstallment.schedule_id.in_(schedule_ids),
            )
        )
    ).all()
    paid = {
        row[0]: int(row[1] or 0)
        for row in await db.execute(
            select(FinancePayment.schedule_id, func.sum(FinancePayment.amount_cents))
            .where(
                FinancePayment.organization_id == org,
                FinancePayment.schedule_id.in_(schedule_ids),
                FinancePayment.voided_at.is_(None),
            )
            .group_by(FinancePayment.schedule_id)
        )
    }
    out: dict[uuid.UUID, tuple[int, InstallmentState]] = {}
    for sid in schedule_ids:
        rows = [i for i in installments if i.schedule_id == sid]
        by_number = {i.number: i for i in rows}
        for a in allocate(
            [(i.number, i.due_on, i.amount_cents) for i in rows], paid.get(sid, 0), today
        ):
            out[by_number[a.number].id] = (a.amount_cents - a.paid_cents, a.state)
    return out


def _days(settings: FinanceReminderSettings | None, kind: Kind) -> int:
    if settings is None:
        return DEFAULT_DAYS[kind]
    return int(getattr(settings, f"{SETTING[kind]}_days"))


# --- scheduler -------------------------------------------------------------------------------


async def create_due(db: AsyncSession, tenant: TenantContext, today: date) -> int:
    """Add the pending reminders due today. Idempotent; runs as the worker."""
    org = tenant.organization_id
    settings = await db.scalar(
        select(FinanceReminderSettings).where(FinanceReminderSettings.organization_id == org)
    )
    schedules = (
        await db.scalars(
            select(FinanceSchedule).where(
                FinanceSchedule.organization_id == org,
                FinanceSchedule.status == "active",
                FinanceSchedule.reminders_paused.is_(False),
            )
        )
    ).all()
    if not schedules:
        return 0
    by_id = {s.id: s for s in schedules}
    owed = await _owed(db, org, list(by_id), today)
    installments = (
        await db.scalars(
            select(FinanceInstallment).where(
                FinanceInstallment.organization_id == org,
                FinanceInstallment.schedule_id.in_(list(by_id)),
            )
        )
    ).all()
    rows = []
    for inst in installments:
        left, state = owed.get(inst.id, (0, InstallmentState.PAID))
        if left <= 0 or state is InstallmentState.PAID:
            continue
        for kind in reminders_due(
            inst.due_on,
            today,
            before_days=_days(settings, "before_due"),
            overdue_days=_days(settings, "overdue"),
        ):
            rows.append(
                {
                    "organization_id": org,
                    "schedule_id": inst.schedule_id,
                    "installment_id": inst.id,
                    "contact_id": by_id[inst.schedule_id].contact_id,
                    "kind": kind,
                    "due_on": inst.due_on,
                    "status": "pending",
                }
            )
    if not rows:
        return 0
    result = await db.execute(
        insert(FinanceReminder)
        .values(rows)
        .on_conflict_do_nothing(constraint="uq_finance_reminders_installment_kind")
        .returning(FinanceReminder.id)
    )
    return len(result.scalars().all())


async def dismiss_for_schedule(
    db: AsyncSession, workspace: WorkspaceAccess, schedule_id: uuid.UUID
) -> None:
    """A paused or cancelled schedule's pending reminders are dismissed."""
    now = datetime.now(UTC)
    await db.execute(
        update(FinanceReminder)
        .where(
            FinanceReminder.organization_id == workspace.tenant.organization_id,
            FinanceReminder.schedule_id == schedule_id,
            FinanceReminder.status.in_(("pending", "skipped")),
        )
        .values(
            status="dismissed",
            skip_reason=None,
            decided_by_user_id=workspace.user.id,
            decided_at=now,
            updated_at=now,
        )
    )


# --- the service -----------------------------------------------------------------------------


class PaymentReminderService:
    def __init__(self, db: AsyncSession, workspace: WorkspaceAccess, today: date) -> None:
        self.db = db
        self.workspace = workspace
        self.tenant = workspace.tenant
        self.org = workspace.tenant.organization_id
        self.today = today

    async def _audit(self, action: str, target_id: uuid.UUID, **details: object) -> None:
        await record_workspace_audit(
            self.db,
            self.workspace,
            action=action,
            target_type="finance_reminder",
            target_id=target_id,
            details=details or None,
        )

    # --- list ------------------------------------------------------------------------------

    async def _out(self, rows: Sequence[FinanceReminder]) -> list[PaymentReminderOut]:
        if not rows:
            return []
        schedule_ids = list({r.schedule_id for r in rows})
        schedules = {
            s.id: s
            for s in (
                await self.db.scalars(
                    select(FinanceSchedule).where(
                        FinanceSchedule.organization_id == self.org,
                        FinanceSchedule.id.in_(schedule_ids),
                    )
                )
            ).all()
        }
        numbers = {
            i.id: i.number
            for i in (
                await self.db.scalars(
                    select(FinanceInstallment).where(
                        FinanceInstallment.organization_id == self.org,
                        FinanceInstallment.id.in_({r.installment_id for r in rows}),
                    )
                )
            ).all()
        }
        owed = await _owed(self.db, self.org, schedule_ids, self.today)
        contacts = await crm.get_contacts(self.db, self.tenant, {r.contact_id for r in rows})
        out = []
        for r in rows:
            contact = contacts.get(r.contact_id)
            schedule = schedules.get(r.schedule_id)
            out.append(
                PaymentReminderOut(
                    id=r.id,
                    kind=r.kind,
                    due_on=r.due_on,
                    status=r.status,
                    channel=r.channel,
                    skip_reason=r.skip_reason,
                    schedule_id=r.schedule_id,
                    label=schedule.label if schedule else "Schedule",
                    installment_number=numbers.get(r.installment_id, 0),
                    owed_cents=owed.get(r.installment_id, (0, InstallmentState.PAID))[0],
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
        self, status: str | None, kind: Kind | None, limit: int, offset: int
    ) -> PaymentReminderList:
        conditions = [FinanceReminder.organization_id == self.org]
        if status is not None:
            conditions.append(FinanceReminder.status == status)
        if kind is not None:
            conditions.append(FinanceReminder.kind == kind)
        total = await self.db.scalar(
            select(func.count()).select_from(FinanceReminder).where(*conditions)
        )
        rows = (
            await self.db.scalars(
                select(FinanceReminder)
                .where(*conditions)
                .order_by(FinanceReminder.due_on, FinanceReminder.id)
                .limit(limit)
                .offset(offset)
            )
        ).all()
        return PaymentReminderList(items=await self._out(rows), total=total or 0)

    async def _row(self, reminder_id: uuid.UUID) -> FinanceReminder | None:
        return await self.db.scalar(
            select(FinanceReminder)
            .where(FinanceReminder.organization_id == self.org, FinanceReminder.id == reminder_id)
            .with_for_update()
        )

    async def dismiss(self, reminder_id: uuid.UUID) -> PaymentReminderOut:
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
        await self._audit("finance.reminder.dismissed", row.id)
        return (await self._out([row]))[0]

    # --- settings --------------------------------------------------------------------------

    async def _settings_row(self) -> FinanceReminderSettings | None:
        return await self.db.scalar(
            select(FinanceReminderSettings).where(
                FinanceReminderSettings.organization_id == self.org
            )
        )

    async def _kind_out(self, row: FinanceReminderSettings | None, kind: Kind) -> KindSettingsOut:
        prefix = SETTING[kind]
        template_id = getattr(row, f"{prefix}_template_id") if row else None
        template = (
            await inbox.whatsapp_template(self.db, self.tenant, template_id)
            if template_id is not None
            else None
        )
        params = list(getattr(row, f"{prefix}_params") or []) if row else []
        message = getattr(row, f"{prefix}_message") if row else None
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

    async def settings(self) -> PaymentReminderSettingsOut:
        row = await self._settings_row()
        return PaymentReminderSettingsOut(
            before_due=await self._kind_out(row, "before_due"),
            overdue=await self._kind_out(row, "overdue"),
            param_keys=list(PARAM_KEYS),
        )

    async def update_settings(self, body: PaymentReminderSettingsIn) -> PaymentReminderSettingsOut:
        if body.before_due.days > 30:
            raise ValidationFailedError(
                "Remind at most 30 days before the due date.",
                details=[
                    ErrorDetail(loc=["body", "before_due", "days"], msg="too many", type="range")
                ],
            )
        for kind in KINDS:
            part: KindSettingsIn = getattr(body, kind)
            if part.template_id is None:
                continue
            template = await inbox.whatsapp_template(self.db, self.tenant, part.template_id)
            if template is None or not template.usable_for_utility:
                raise ValidationFailedError(
                    "Choose an approved, supported WhatsApp utility template.",
                    details=[
                        ErrorDetail(
                            loc=["body", kind, "template_id"], msg="not usable", type="template"
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
                        ErrorDetail(loc=["body", kind, "params"], msg="mismatch", type="params")
                    ],
                )
        row = await self._settings_row()
        if row is None:
            row = FinanceReminderSettings(organization_id=self.org)
            self.db.add(row)
        for kind in KINDS:
            part = getattr(body, kind)
            prefix = SETTING[kind]
            setattr(row, f"{prefix}_days", part.days)
            setattr(row, f"{prefix}_message", part.message)
            setattr(row, f"{prefix}_template_id", part.template_id)
            setattr(row, f"{prefix}_params", list(part.params) if part.template_id else [])
        row.updated_by_user_id = self.workspace.user.id
        row.updated_at = datetime.now(UTC)
        await self.db.flush()
        await record_workspace_audit(
            self.db,
            self.workspace,
            action="finance.reminder_settings.updated",
            target_type="finance_reminder_settings",
            target_id=self.org,
        )
        return await self.settings()

    # --- sending ---------------------------------------------------------------------------

    async def send(self, body: PaymentReminderSendRequest) -> PaymentReminderSendResult:
        settings = await self.settings()
        sent: list[uuid.UUID] = []
        skipped: list[PaymentReminderSkip] = []
        for reminder_id in dict.fromkeys(body.reminder_ids):
            outcome = await self._send_one(reminder_id, settings)
            if isinstance(outcome, PaymentReminderSkip):
                skipped.append(outcome)
            else:
                sent.append(outcome)
        return PaymentReminderSendResult(sent=sent, skipped=skipped)

    async def _mark_skipped(self, row: FinanceReminder, reason: str) -> PaymentReminderSkip:
        row.status = "skipped"
        row.skip_reason = reason
        row.updated_at = datetime.now(UTC)
        await self.db.flush()
        return _skip(row.id, reason)

    async def _send_one(
        self, reminder_id: uuid.UUID, settings: PaymentReminderSettingsOut
    ) -> uuid.UUID | PaymentReminderSkip:
        row = await self._row(reminder_id)
        if row is None:
            return _skip(reminder_id, "not_found")
        if row.status not in ("pending", "skipped"):
            return _skip(row.id, "already_decided")
        schedule = await self.db.scalar(
            select(FinanceSchedule).where(
                FinanceSchedule.organization_id == self.org, FinanceSchedule.id == row.schedule_id
            )
        )
        if schedule is None or schedule.status != "active" or schedule.reminders_paused:
            return await self._mark_skipped(row, "paused")
        left, state = (await _owed(self.db, self.org, [schedule.id], self.today)).get(
            row.installment_id, (0, InstallmentState.PAID)
        )
        if left <= 0 or state is InstallmentState.PAID:
            return await self._mark_skipped(row, "paid")
        contact = (await crm.get_contacts(self.db, self.tenant, [row.contact_id])).get(
            row.contact_id
        )
        if contact is None:
            return await self._mark_skipped(row, "no_channel")
        kind: Kind = row.kind  # type: ignore[assignment]
        config: KindSettingsOut = getattr(settings, kind)
        name = _first_name(contact.full_name)
        text_body = render(
            config.message, name=name, car=schedule.label, amount=left, due=row.due_on
        )
        subject = render(SUBJECT[kind], name=name, car=schedule.label, amount=left, due=row.due_on)
        template = (
            await inbox.whatsapp_template(self.db, self.tenant, config.template_id)
            if config.template_ready and config.template_id is not None
            else None
        )
        values = {
            "first_name": name,
            "vehicle": schedule.label,
            "amount": euros(left),
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
                    idempotency_key=f"payment-reminder-{row.id}",
                    template=inbox.TemplateChoice(
                        template.id, template.channel_id, [values[k] for k in config.params]
                    )
                    if template is not None
                    else None,
                )
        except inbox.NoChannelError:
            return await self._mark_skipped(row, "no_channel")
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
        await self._audit("finance.reminder.sent", row.id, kind=row.kind, channel=delivered.channel)
        return row.id
