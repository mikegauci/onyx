"""Daily owner summary rules (VA-010): local-day bounds, when it is due and the message."""

from datetime import UTC, date, datetime, time
from zoneinfo import ZoneInfo

from app.core.insights import daily

MALTA = ZoneInfo("Europe/Malta")


def test_day_bounds_follow_malta_time_across_dst() -> None:
    start, end = daily.day_bounds(date(2026, 11, 26), MALTA)
    assert (start, end) == (
        datetime(2026, 11, 25, 23, tzinfo=UTC),
        datetime(2026, 11, 26, 23, tzinfo=UTC),
    )
    spring = daily.day_bounds(date(2026, 3, 29), MALTA)  # clocks go forward: 23 hours
    assert (spring[1] - spring[0]).total_seconds() == 23 * 3600
    autumn = daily.day_bounds(date(2026, 10, 25), MALTA)  # clocks go back: 25 hours
    assert (autumn[1] - autumn[0]).total_seconds() == 25 * 3600


def test_due_from_send_time_until_local_midnight_only() -> None:
    seven = time(19, 0)
    assert daily.due_date(datetime(2026, 11, 26, 17, 59, tzinfo=UTC), MALTA, seven) is None
    assert daily.due_date(datetime(2026, 11, 26, 18, 0, tzinfo=UTC), MALTA, seven) == date(
        2026, 11, 26
    )
    # 23:30 UTC is already the 27th in Malta and before 19:00 there: nothing for the 26th.
    assert daily.due_date(datetime(2026, 11, 26, 23, 30, tzinfo=UTC), MALTA, seven) is None


def test_message_shows_figures_and_missing_sources_never_as_zero() -> None:
    figures = daily.Figures(
        day=date(2026, 11, 26),
        enquiries=daily.Enquiries(14, {"whatsapp": 9, "email": 3, "web": 0}, 2),
        deals=daily.Deals(reserved=2, sold=1),
        payments=daily.Payments(count=3, total_cents=145_000),
        listings=None,
        missing={"listings": daily.Missing.NOT_SET_UP, "social": daily.Missing.NOT_CONNECTED},
    )
    assert daily.render("Ventur", figures).splitlines() == [
        "Ventur — Thursday 26/11/2026",
        "Enquiries: 14 (email 3, WhatsApp 9, missed calls 2)",
        "Reserved: 2 · Sold: 1",
        "Payments: 3 recorded, €1,450.00",
        "Listings: not set up",
        "Facebook/Instagram: not connected",
    ]
    line = daily.one_line(figures)
    assert "\n" not in line
    assert line.startswith("Enquiries: 14")


def test_figures_round_trip_as_json() -> None:
    figures = daily.Figures(
        day=date(2026, 11, 26),
        listings=daily.Listings(added=2, removed=1, available=37),
        missing={"enquiries": daily.Missing.NOT_CONNECTED},
    )
    data = figures.to_json()
    assert data["day"] == "2026-11-26"
    assert data["listings"] == {"added": 2, "removed": 1, "available": 37}
    assert data["missing"] == {"enquiries": "not_connected"}
    assert "Listings: 2 added, 1 removed (37 available)" in daily.render("V", figures)
