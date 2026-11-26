"""Repayment schedule rules (VA-008): pure functions, no database.

- ``plan`` splits the total into monthly installments that add up exactly to it.
- ``allocate`` applies the payments to the installments in order, oldest first.
- ``state`` says whether an installment is paid, part paid, overdue, due today or upcoming.
"""

import calendar
import enum
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date


class InstallmentState(enum.StrEnum):
    PAID = "paid"
    PART_PAID = "part_paid"
    OVERDUE = "overdue"
    DUE_TODAY = "due_today"
    UPCOMING = "upcoming"


class PlanError(ValueError):
    pass


@dataclass(frozen=True)
class PlannedInstallment:
    number: int
    due_on: date
    amount_cents: int


def add_months(day: date, months: int) -> date:
    total = day.month - 1 + months
    year, month = day.year + total // 12, total % 12 + 1
    return date(year, month, min(day.day, calendar.monthrange(year, month)[1]))


def plan(
    total_cents: int, term_months: int, first_due_on: date, monthly_cents: int | None = None
) -> list[PlannedInstallment]:
    """``term_months`` installments a month apart. Each is ``monthly_cents`` (default: the
    total split evenly, rounded down); the last takes the difference, so they add up to the
    total."""
    if total_cents <= 0:
        raise PlanError("The amount to repay must be more than zero.")
    if not 1 <= term_months <= 120:
        raise PlanError("The term must be between 1 and 120 months.")
    monthly = monthly_cents if monthly_cents is not None else total_cents // term_months
    if monthly <= 0:
        raise PlanError("The monthly amount must be more than zero.")
    last = total_cents - monthly * (term_months - 1)
    if last <= 0:
        raise PlanError("The monthly amount is too high for this total and term.")
    return [
        PlannedInstallment(
            number=n + 1,
            due_on=add_months(first_due_on, n),
            amount_cents=monthly if n < term_months - 1 else last,
        )
        for n in range(term_months)
    ]


@dataclass(frozen=True)
class Allocated:
    number: int
    due_on: date
    amount_cents: int
    paid_cents: int
    state: InstallmentState


def state(due_on: date, amount_cents: int, paid_cents: int, today: date) -> InstallmentState:
    if paid_cents >= amount_cents:
        return InstallmentState.PAID
    if due_on < today:
        return InstallmentState.OVERDUE
    if paid_cents > 0:
        return InstallmentState.PART_PAID
    if due_on == today:
        return InstallmentState.DUE_TODAY
    return InstallmentState.UPCOMING


def allocate(
    installments: Sequence[tuple[int, date, int]], paid_total_cents: int, today: date
) -> list[Allocated]:
    """Installments as (number, due_on, amount), paid in number order by the paid total."""
    left = paid_total_cents
    out = []
    for number, due_on, amount in sorted(installments):
        paid = min(amount, max(left, 0))
        left -= paid
        out.append(Allocated(number, due_on, amount, paid, state(due_on, amount, paid, today)))
    return out


OVERDUE_GRACE_DAYS = 30  # an overdue reminder can still be created this long after it was due


def reminders_due(due_on: date, today: date, *, before_days: int, overdue_days: int) -> list[str]:
    """Which reminders an unpaid installment should have today: ``before_due`` from
    ``before_days`` before the due date until the date itself; ``overdue`` from ``overdue_days``
    after it, for ``OVERDUE_GRACE_DAYS``."""
    kinds = []
    if (due_on - today).days in range(0, before_days + 1):
        kinds.append("before_due")
    late = (today - due_on).days
    if overdue_days <= late <= overdue_days + OVERDUE_GRACE_DAYS:
        kinds.append("overdue")
    return kinds
