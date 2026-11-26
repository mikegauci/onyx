"""Due-date rules for customer-car reminders (VA-009 part 2): pure, no database."""

from datetime import date

from app.modules.automotive.models import ReminderKind
from app.modules.automotive.reminders import add_months, due_dates, in_window, render


def _due(**overrides: object) -> dict[ReminderKind, date | None]:
    values: dict[str, object] = {
        "licence_due_on": date(2027, 3, 1),
        "dealer_handles_licence": True,
        "insurance_due_on": date(2027, 5, 10),
        "dealer_handles_insurance": False,
        "last_service_on": None,
        "collected_on": date(2026, 11, 26),
        "service_interval_months": 12,
        **overrides,
    }
    return due_dates(**values)  # type: ignore[arg-type]


def test_months_keep_the_day_or_use_the_months_last_day() -> None:
    assert add_months(date(2026, 1, 31), 1) == date(2026, 2, 28)
    assert add_months(date(2024, 1, 31), 1) == date(2024, 2, 29)
    assert add_months(date(2026, 11, 26), 12) == date(2027, 11, 26)
    assert add_months(date(2026, 12, 15), 3) == date(2027, 3, 15)


def test_licence_and_insurance_only_when_the_dealer_handles_them() -> None:
    due = _due()
    assert due[ReminderKind.LICENCE] == date(2027, 3, 1)
    assert due[ReminderKind.INSURANCE] is None  # the customer handles their own insurance
    assert _due(dealer_handles_licence=False)[ReminderKind.LICENCE] is None
    assert _due(licence_due_on=None)[ReminderKind.LICENCE] is None


def test_service_is_due_an_interval_after_the_last_service_or_collection() -> None:
    assert _due()[ReminderKind.SERVICE] == date(2027, 11, 26)
    assert _due(last_service_on=date(2027, 2, 1))[ReminderKind.SERVICE] == date(2028, 2, 1)
    assert _due(service_interval_months=6)[ReminderKind.SERVICE] == date(2027, 5, 26)
    assert _due(collected_on=None)[ReminderKind.SERVICE] is None


def test_the_window_opens_days_before_and_closes_30_days_after() -> None:
    due = date(2027, 3, 1)
    assert not in_window(due, date(2027, 1, 29), 30)
    assert in_window(due, date(2027, 1, 30), 30)
    assert in_window(due, date(2027, 3, 31), 30)
    assert not in_window(due, date(2027, 4, 1), 30)


def test_the_message_drops_a_missing_registration() -> None:
    text = "Hi {name}, your {car} ({registration}) is due on {due}."
    assert render(
        text, name="Clara", car="VW Golf", registration="ABC 123", due=date(2027, 3, 1)
    ) == ("Hi Clara, your VW Golf (ABC 123) is due on 01/03/2027.")
    assert render(text, name="Clara", car="VW Golf", registration=None, due=date(2027, 3, 1)) == (
        "Hi Clara, your VW Golf is due on 01/03/2027."
    )
