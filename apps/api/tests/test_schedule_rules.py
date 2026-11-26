"""Repayment schedule rules (VA-008): pure, no database."""

from datetime import date

import pytest

from app.modules.deals.schedule_rules import InstallmentState, PlanError, allocate, plan

TODAY = date(2027, 3, 15)


def test_installments_add_up_exactly_to_the_total() -> None:
    rows = plan(1_000_000, 3, date(2027, 1, 31))
    assert [(r.number, r.due_on, r.amount_cents) for r in rows] == [
        (1, date(2027, 1, 31), 333_333),
        (2, date(2027, 2, 28), 333_333),
        (3, date(2027, 3, 31), 333_334),
    ]
    assert sum(r.amount_cents for r in rows) == 1_000_000


def test_a_given_monthly_amount_leaves_the_rest_to_the_last_installment() -> None:
    rows = plan(1_000_000, 4, date(2027, 1, 1), monthly_cents=260_000)
    assert [r.amount_cents for r in rows] == [260_000, 260_000, 260_000, 220_000]
    with pytest.raises(PlanError):
        plan(1_000_000, 4, date(2027, 1, 1), monthly_cents=340_000)  # nothing left for the last
    with pytest.raises(PlanError):
        plan(0, 4, date(2027, 1, 1))


def test_payments_pay_the_oldest_installments_first() -> None:
    rows = [(1, date(2027, 2, 1), 100), (2, date(2027, 3, 1), 100), (3, date(2027, 4, 1), 100)]
    states = [(a.paid_cents, a.state) for a in allocate(rows, 150, TODAY)]
    assert states == [
        (100, InstallmentState.PAID),
        (50, InstallmentState.OVERDUE),  # part paid but past its date
        (0, InstallmentState.UPCOMING),
    ]
    assert allocate(rows, 400, TODAY)[2].state is InstallmentState.PAID  # overpayment is capped


def test_states_around_the_due_date() -> None:
    rows = [(1, TODAY, 100), (2, date(2027, 4, 15), 100)]
    assert [a.state for a in allocate(rows, 0, TODAY)] == [
        InstallmentState.DUE_TODAY,
        InstallmentState.UPCOMING,
    ]
    assert allocate(rows, 150, TODAY)[1].state is InstallmentState.PART_PAID
