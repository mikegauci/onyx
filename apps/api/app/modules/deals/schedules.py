"""In-house finance schedules and payments (VA-008 part 1).

Staff enter a customer's repayment plan (prefilled from a deal's approved finance application)
and record the payments they receive; Onyx never takes payments. Installments add up exactly
to the total (``schedule_rules.plan``). Payments pay the installments oldest first
(``schedule_rules.allocate``), so each installment's state follows from the payments. A
schedule completes when everything is paid and reopens if a payment is voided. Payments are
voided with a reason, never deleted.

Everyone with deals access sees schedules; changing them and recording payments needs
``finance.manage`` (owners and admins). Dates are the workspace's local date.
"""

import enum
import uuid
from collections.abc import Sequence
from datetime import UTC, date, datetime
from typing import Annotated
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field, StringConstraints
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit.record import record_workspace_audit
from app.core.auth.deps import WorkspaceAccess
from app.core.errors import ConflictError, ErrorDetail, NotFoundError, ValidationFailedError
from app.modules.crm import public as crm
from app.modules.deals.finance_rules import ApplicationStatus
from app.modules.deals.models import (
    Deal,
    FinanceApplication,
    FinanceInstallment,
    FinancePayment,
    FinanceSchedule,
)
from app.modules.deals.schedule_rules import InstallmentState, PlanError, allocate, plan

Text200 = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
Text300 = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=300)]
Text500 = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]
Cents = Annotated[int, Field(gt=0, le=100_000_000)]


class ScheduleStatus(enum.StrEnum):
    ACTIVE = "active"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class PaymentMethod(enum.StrEnum):
    CASH = "cash"
    BANK_TRANSFER = "bank_transfer"
    CARD = "card"
    CHEQUE = "cheque"
    OTHER = "other"


# --- schemas ---------------------------------------------------------------------------------


class _Input(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ScheduleIn(_Input):
    deal_id: uuid.UUID | None = Field(
        default=None, description="Prefills the contact, car and amounts from the deal"
    )
    contact_id: uuid.UUID | None = Field(default=None, description="Needed without a deal")
    application_id: uuid.UUID | None = Field(
        default=None, description="Defaults to the deal's approved finance application"
    )
    label: Text200 | None = Field(default=None, description="The car; defaults to the deal title")
    total_cents: Cents | None = Field(
        default=None, description="Amount to repay; defaults to the application's estimate"
    )
    term_months: int | None = Field(default=None, ge=1, le=120)
    monthly_cents: Cents | None = None
    first_due_on: date
    note: Text500 | None = None


class ScheduleUpdate(_Input):
    label: Text200
    note: Text500 | None = None
    reminders_paused: bool = False
    cancelled: bool = Field(default=False, description="Cancel (or reopen) the schedule")


class InstallmentUpdate(_Input):
    due_on: date
    amount_cents: Cents


class PaymentIn(_Input):
    amount_cents: Cents
    received_on: date
    method: PaymentMethod
    note: Text300 | None = None


class PaymentVoid(_Input):
    reason: Text300


class InstallmentOut(BaseModel):
    id: uuid.UUID
    number: int
    due_on: date
    amount_cents: int
    paid_cents: int
    state: InstallmentState


class PaymentOut(BaseModel):
    id: uuid.UUID
    amount_cents: int
    received_on: date
    method: PaymentMethod
    note: str | None
    voided: bool
    void_reason: str | None
    created_at: datetime


class ScheduleSummary(BaseModel):
    id: uuid.UUID
    contact_id: uuid.UUID
    contact_name: str
    deal_id: uuid.UUID | None
    application_id: uuid.UUID | None
    label: str
    status: ScheduleStatus
    reminders_paused: bool
    total_cents: int
    monthly_cents: int
    term_months: int
    paid_cents: int
    outstanding_cents: int
    next_due_on: date | None
    next_due_cents: int | None
    overdue_count: int
    overdue_cents: int


class ScheduleDetail(ScheduleSummary):
    first_due_on: date
    note: str | None
    installments: list[InstallmentOut]
    payments: list[PaymentOut]


class ScheduleList(BaseModel):
    items: list[ScheduleSummary]


def workspace_today(workspace: WorkspaceAccess) -> date:
    """Today's date in the workspace's timezone."""
    try:
        zone = ZoneInfo(workspace.organization.timezone)
    except (KeyError, ValueError):  # pragma: no cover - timezones are validated on save
        zone = ZoneInfo("UTC")
    return datetime.now(zone).date()


def _invalid(field: str, message: str) -> ValidationFailedError:
    return ValidationFailedError(
        message, details=[ErrorDetail(loc=["body", field], msg=message, type="invalid")]
    )


class ScheduleService:
    def __init__(self, db: AsyncSession, workspace: WorkspaceAccess) -> None:
        self.db = db
        self.workspace = workspace
        self.tenant = workspace.tenant
        self.org = workspace.tenant.organization_id

    def _today(self) -> date:
        return workspace_today(self.workspace)

    async def _audit(self, action: str, target_id: uuid.UUID, **details: object) -> None:
        await record_workspace_audit(
            self.db,
            self.workspace,
            action=action,
            target_type="finance_schedule",
            target_id=target_id,
            details=details or None,
        )

    # --- reading ---------------------------------------------------------------------------

    async def _schedule(self, schedule_id: uuid.UUID, *, lock: bool = False) -> FinanceSchedule:
        query = select(FinanceSchedule).where(
            FinanceSchedule.organization_id == self.org, FinanceSchedule.id == schedule_id
        )
        found = await self.db.scalar(query.with_for_update() if lock else query)
        if found is None:
            raise NotFoundError("Payment schedule not found.")
        return found

    async def _installments(
        self, ids: Sequence[uuid.UUID]
    ) -> dict[uuid.UUID, list[FinanceInstallment]]:
        rows = (
            await self.db.scalars(
                select(FinanceInstallment)
                .where(
                    FinanceInstallment.organization_id == self.org,
                    FinanceInstallment.schedule_id.in_(ids),
                )
                .order_by(FinanceInstallment.number)
            )
        ).all()
        out: dict[uuid.UUID, list[FinanceInstallment]] = {i: [] for i in ids}
        for row in rows:
            out[row.schedule_id].append(row)
        return out

    async def _paid(self, ids: Sequence[uuid.UUID]) -> dict[uuid.UUID, int]:
        rows = await self.db.execute(
            select(FinancePayment.schedule_id, func.sum(FinancePayment.amount_cents))
            .where(
                FinancePayment.organization_id == self.org,
                FinancePayment.schedule_id.in_(ids),
                FinancePayment.voided_at.is_(None),
            )
            .group_by(FinancePayment.schedule_id)
        )
        return {row[0]: int(row[1] or 0) for row in rows}

    def _summary(
        self,
        s: FinanceSchedule,
        installments: list[FinanceInstallment],
        paid: int,
        contact_name: str,
    ) -> tuple[ScheduleSummary, list[InstallmentOut]]:
        today = self._today()
        allocated = allocate(
            [(i.number, i.due_on, i.amount_cents) for i in installments], paid, today
        )
        by_number = {i.number: i for i in installments}
        rows = [
            InstallmentOut(
                id=by_number[a.number].id,
                number=a.number,
                due_on=a.due_on,
                amount_cents=a.amount_cents,
                paid_cents=a.paid_cents,
                state=a.state,
            )
            for a in allocated
        ]
        total = sum(i.amount_cents for i in installments)
        unpaid = [r for r in rows if r.state is not InstallmentState.PAID]
        overdue = [r for r in rows if r.state is InstallmentState.OVERDUE]
        upcoming = next((r for r in unpaid if r.state is not InstallmentState.OVERDUE), None)
        summary = ScheduleSummary(
            id=s.id,
            contact_id=s.contact_id,
            contact_name=contact_name,
            deal_id=s.deal_id,
            application_id=s.application_id,
            label=s.label,
            status=ScheduleStatus(s.status),
            reminders_paused=s.reminders_paused,
            total_cents=total,
            monthly_cents=s.monthly_cents,
            term_months=s.term_months,
            paid_cents=min(paid, total),
            outstanding_cents=max(total - paid, 0),
            next_due_on=upcoming.due_on if upcoming else None,
            next_due_cents=(upcoming.amount_cents - upcoming.paid_cents) if upcoming else None,
            overdue_count=len(overdue),
            overdue_cents=sum(r.amount_cents - r.paid_cents for r in overdue),
        )
        return summary, rows

    async def list(self, status: ScheduleStatus | None, overdue_only: bool) -> ScheduleList:
        query = select(FinanceSchedule).where(FinanceSchedule.organization_id == self.org)
        if status is not None:
            query = query.where(FinanceSchedule.status == status.value)
        schedules = (await self.db.scalars(query.order_by(FinanceSchedule.created_at.desc()))).all()
        ids = [s.id for s in schedules]
        installments = await self._installments(ids)
        paid = await self._paid(ids)
        contacts = await crm.get_contacts(self.db, self.tenant, {s.contact_id for s in schedules})
        items = []
        for s in schedules:
            name = c.full_name if (c := contacts.get(s.contact_id)) else "Unknown"
            summary, _ = self._summary(s, installments[s.id], paid.get(s.id, 0), name)
            if overdue_only and summary.overdue_count == 0:
                continue
            items.append(summary)
        return ScheduleList(items=items)

    async def detail(self, schedule_id: uuid.UUID) -> ScheduleDetail:
        s = await self._schedule(schedule_id)
        installments = (await self._installments([s.id]))[s.id]
        paid = (await self._paid([s.id])).get(s.id, 0)
        contact = (await crm.get_contacts(self.db, self.tenant, [s.contact_id])).get(s.contact_id)
        summary, rows = self._summary(
            s, installments, paid, contact.full_name if contact else "Unknown"
        )
        payments = (
            await self.db.scalars(
                select(FinancePayment)
                .where(
                    FinancePayment.organization_id == self.org,
                    FinancePayment.schedule_id == s.id,
                )
                .order_by(FinancePayment.received_on.desc(), FinancePayment.created_at.desc())
            )
        ).all()
        return ScheduleDetail(
            **summary.model_dump(),
            first_due_on=s.first_due_on,
            note=s.note,
            installments=rows,
            payments=[
                PaymentOut(
                    id=p.id,
                    amount_cents=p.amount_cents,
                    received_on=p.received_on,
                    method=PaymentMethod(p.method),
                    note=p.note,
                    voided=p.voided_at is not None,
                    void_reason=p.void_reason,
                    created_at=p.created_at,
                )
                for p in payments
            ],
        )

    # --- creating and changing -------------------------------------------------------------

    async def _application(self, body: ScheduleIn, deal: Deal | None) -> FinanceApplication | None:
        if body.application_id is not None:
            app = await self.db.scalar(
                select(FinanceApplication).where(
                    FinanceApplication.organization_id == self.org,
                    FinanceApplication.id == body.application_id,
                )
            )
            if app is None:
                raise _invalid("application_id", "Finance application not found.")
            return app
        if deal is None:
            return None
        found: FinanceApplication | None = await self.db.scalar(
            select(FinanceApplication)
            .where(
                FinanceApplication.organization_id == self.org,
                FinanceApplication.deal_id == deal.id,
                FinanceApplication.status == ApplicationStatus.APPROVED,
            )
            .order_by(FinanceApplication.updated_at.desc())
            .limit(1)
        )
        return found

    async def create(self, body: ScheduleIn) -> ScheduleDetail:
        deal = None
        if body.deal_id is not None:
            deal = await self.db.scalar(
                select(Deal).where(Deal.organization_id == self.org, Deal.id == body.deal_id)
            )
            if deal is None:
                raise _invalid("deal_id", "Deal not found.")
        contact_id = deal.contact_id if deal is not None else body.contact_id
        if contact_id is None:
            raise _invalid("contact_id", "Choose the customer or the deal.")
        if body.contact_id is not None and body.contact_id != contact_id:
            raise _invalid("contact_id", "The deal belongs to a different customer.")
        if not (await crm.get_contacts(self.db, self.tenant, [contact_id])):
            raise _invalid("contact_id", "Customer not found.")
        app = await self._application(body, deal)
        if app is not None and app.contact_id != contact_id:
            raise _invalid("application_id", "The application belongs to a different customer.")
        estimate = app.estimate if app is not None else {}
        total = body.total_cents or estimate.get("total_cents")
        term = body.term_months or estimate.get("term_months")
        monthly = body.monthly_cents or (
            estimate.get("monthly_cents") if body.total_cents is None else None
        )
        if not total:
            raise _invalid("total_cents", "Enter the amount to repay.")
        if not term:
            raise _invalid("term_months", "Enter the term in months.")
        try:
            planned = plan(
                int(total), int(term), body.first_due_on, int(monthly) if monthly else None
            )
        except PlanError as exc:
            raise _invalid("monthly_cents", str(exc)) from exc
        label = (
            body.label
            or (deal.title if deal is not None else None)
            or (app.vehicle_label if app is not None and app.vehicle_label else None)
        )
        if not label:
            raise _invalid("label", "Describe the car.")
        if deal is not None:
            taken = await self.db.scalar(
                select(FinanceSchedule.id).where(
                    FinanceSchedule.organization_id == self.org, FinanceSchedule.deal_id == deal.id
                )
            )
            if taken is not None:
                raise ConflictError("This deal already has a payment schedule.")
        schedule = FinanceSchedule(
            organization_id=self.org,
            contact_id=contact_id,
            deal_id=deal.id if deal is not None else None,
            application_id=app.id if app is not None else None,
            label=label[:200],
            total_cents=int(total),
            term_months=int(term),
            monthly_cents=planned[0].amount_cents,
            first_due_on=body.first_due_on,
            status=ScheduleStatus.ACTIVE.value,
            note=body.note,
            created_by_user_id=self.workspace.user.id,
        )
        self.db.add(schedule)
        await self.db.flush()
        for p in planned:
            self.db.add(
                FinanceInstallment(
                    organization_id=self.org,
                    schedule_id=schedule.id,
                    number=p.number,
                    due_on=p.due_on,
                    amount_cents=p.amount_cents,
                )
            )
        await self.db.flush()
        await self._audit(
            "finance.schedule.created",
            schedule.id,
            deal_id=str(deal.id) if deal else None,
            term_months=int(term),
        )
        return await self.detail(schedule.id)

    async def update(self, schedule_id: uuid.UUID, body: ScheduleUpdate) -> ScheduleDetail:
        s = await self._schedule(schedule_id, lock=True)
        s.label = body.label
        s.note = body.note
        s.reminders_paused = body.reminders_paused
        if body.cancelled:
            s.status = ScheduleStatus.CANCELLED.value
        elif s.status == ScheduleStatus.CANCELLED.value:
            s.status = ScheduleStatus.ACTIVE.value
        s.updated_at = datetime.now(UTC)
        await self.db.flush()
        await self._refresh_status(s)
        if s.reminders_paused or s.status != ScheduleStatus.ACTIVE.value:
            from app.modules.deals.payment_reminders import dismiss_for_schedule

            await dismiss_for_schedule(self.db, self.workspace, s.id)
        await self._audit(
            "finance.schedule.updated", s.id, status=s.status, reminders_paused=s.reminders_paused
        )
        return await self.detail(s.id)

    async def update_installment(
        self, schedule_id: uuid.UUID, installment_id: uuid.UUID, body: InstallmentUpdate
    ) -> ScheduleDetail:
        s = await self._schedule(schedule_id, lock=True)
        row = await self.db.scalar(
            select(FinanceInstallment).where(
                FinanceInstallment.organization_id == self.org,
                FinanceInstallment.schedule_id == s.id,
                FinanceInstallment.id == installment_id,
            )
        )
        if row is None:
            raise NotFoundError("Installment not found.")
        row.due_on = body.due_on
        row.amount_cents = body.amount_cents
        row.updated_at = datetime.now(UTC)
        await self.db.flush()
        s.total_cents = int(
            await self.db.scalar(
                select(func.sum(FinanceInstallment.amount_cents)).where(
                    FinanceInstallment.organization_id == self.org,
                    FinanceInstallment.schedule_id == s.id,
                )
            )
            or 0
        )
        s.updated_at = datetime.now(UTC)
        await self.db.flush()
        await self._refresh_status(s)
        await self._audit(
            "finance.installment.updated", s.id, number=row.number, amount_cents=body.amount_cents
        )
        return await self.detail(s.id)

    async def _refresh_status(self, s: FinanceSchedule) -> None:
        """Completed when everything is paid; active again if not (cancelled stays)."""
        if s.status == ScheduleStatus.CANCELLED.value:
            return
        paid = (await self._paid([s.id])).get(s.id, 0)
        s.status = (
            ScheduleStatus.COMPLETED.value if paid >= s.total_cents else ScheduleStatus.ACTIVE.value
        )
        await self.db.flush()

    # --- payments --------------------------------------------------------------------------

    async def record_payment(self, schedule_id: uuid.UUID, body: PaymentIn) -> ScheduleDetail:
        s = await self._schedule(schedule_id, lock=True)
        if s.status == ScheduleStatus.CANCELLED.value:
            raise ConflictError("This schedule is cancelled. Reopen it first.")
        if body.received_on > self._today():
            raise _invalid("received_on", "The payment date cannot be in the future.")
        payment = FinancePayment(
            organization_id=self.org,
            schedule_id=s.id,
            amount_cents=body.amount_cents,
            received_on=body.received_on,
            method=body.method.value,
            note=body.note,
            recorded_by_user_id=self.workspace.user.id,
        )
        self.db.add(payment)
        await self.db.flush()
        await self._refresh_status(s)
        await self._audit(
            "finance.payment.recorded",
            s.id,
            payment_id=str(payment.id),
            amount_cents=body.amount_cents,
            method=body.method.value,
        )
        return await self.detail(s.id)

    async def void_payment(
        self, schedule_id: uuid.UUID, payment_id: uuid.UUID, body: PaymentVoid
    ) -> ScheduleDetail:
        s = await self._schedule(schedule_id, lock=True)
        payment = await self.db.scalar(
            select(FinancePayment)
            .where(
                FinancePayment.organization_id == self.org,
                FinancePayment.schedule_id == s.id,
                FinancePayment.id == payment_id,
            )
            .with_for_update()
        )
        if payment is None:
            raise NotFoundError("Payment not found.")
        if payment.voided_at is not None:
            raise ConflictError("This payment was already voided.")
        payment.voided_at = datetime.now(UTC)
        payment.voided_by_user_id = self.workspace.user.id
        payment.void_reason = body.reason
        await self.db.flush()
        await self._refresh_status(s)
        await self._audit(
            "finance.payment.voided",
            s.id,
            payment_id=str(payment.id),
            amount_cents=payment.amount_cents,
        )
        return await self.detail(s.id)
