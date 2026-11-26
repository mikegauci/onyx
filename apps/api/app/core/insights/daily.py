"""Daily owner summary (VA-010): pure rules for the day, when it is due and the message text.

A section either has figures or is missing with a reason. A missing source is shown as missing,
never as zero. The message carries counts and amounts only: no names, numbers or message text.
"""

import enum
from dataclasses import asdict, dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

SECTIONS = ("enquiries", "deals", "payments", "listings", "social")
CHANNEL_LABELS = {"whatsapp": "WhatsApp", "email": "email", "web": "web chat", "manual": "manual"}


class Missing(enum.StrEnum):
    NOT_SET_UP = "not_set_up"  # the module is off
    NOT_CONNECTED = "not_connected"  # no channel or integration to read from


MISSING_TEXT = {Missing.NOT_SET_UP: "not set up", Missing.NOT_CONNECTED: "not connected"}


@dataclass(frozen=True)
class Enquiries:
    total: int
    by_channel: dict[str, int]
    missed_calls: int


@dataclass(frozen=True)
class Deals:
    reserved: int
    sold: int


@dataclass(frozen=True)
class Payments:
    count: int
    total_cents: int


@dataclass(frozen=True)
class Listings:
    added: int
    removed: int
    available: int


@dataclass(frozen=True)
class Figures:
    day: date
    enquiries: Enquiries | None = None
    deals: Deals | None = None
    payments: Payments | None = None
    listings: Listings | None = None
    missing: dict[str, Missing] = field(default_factory=dict)

    def to_json(self) -> dict[str, Any]:
        data = asdict(self)
        data["day"] = self.day.isoformat()
        data["missing"] = {k: v.value for k, v in self.missing.items()}
        return data


def zone_of(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except (KeyError, ValueError):  # pragma: no cover - timezones are validated on save
        return ZoneInfo("UTC")


def day_bounds(day: date, zone: ZoneInfo) -> tuple[datetime, datetime]:
    """The local calendar day as UTC instants, [start, end). 23 or 25 hours around DST."""
    start = datetime.combine(day, time.min, zone)
    end = datetime.combine(day + timedelta(days=1), time.min, zone)
    return start.astimezone(UTC), end.astimezone(UTC)


def due_date(now: datetime, zone: ZoneInfo, send_at: time) -> date | None:
    """The local date to send for, once the local time has reached ``send_at``; else None.

    A late run still sends later the same local day; after midnight it is the next day's turn,
    so a missed day is never sent the following morning.
    """
    local = now.astimezone(zone)
    return local.date() if local.time().replace(tzinfo=None) >= send_at else None


def euros(cents: int) -> str:
    whole, part = divmod(abs(cents), 100)
    return f"{'-' if cents < 0 else ''}€{whole:,}.{part:02d}"


def _missing(figures: Figures, section: str) -> str:
    return MISSING_TEXT[figures.missing.get(section, Missing.NOT_SET_UP)]


def lines(figures: Figures) -> list[str]:
    """One line per section, in order."""
    out: list[str] = []
    e = figures.enquiries
    if e is None:
        out.append(f"Enquiries: {_missing(figures, 'enquiries')}")
    else:
        parts = [f"{CHANNEL_LABELS.get(k, k)} {n}" for k, n in sorted(e.by_channel.items()) if n]
        if e.missed_calls:
            parts.append(f"missed calls {e.missed_calls}")
        detail = f" ({', '.join(parts)})" if parts else ""
        out.append(f"Enquiries: {e.total}{detail}")
    d = figures.deals
    out.append(
        f"Reserved: {d.reserved} · Sold: {d.sold}"
        if d is not None
        else f"Reserved and sold: {_missing(figures, 'deals')}"
    )
    p = figures.payments
    out.append(
        f"Payments: {p.count} recorded, {euros(p.total_cents)}"
        if p is not None
        else f"Payments: {_missing(figures, 'payments')}"
    )
    li = figures.listings
    out.append(
        f"Listings: {li.added} added, {li.removed} removed ({li.available} available)"
        if li is not None
        else f"Listings: {_missing(figures, 'listings')}"
    )
    out.append(f"Facebook/Instagram: {_missing(figures, 'social')}")
    return out


def heading(workspace_name: str, day: date) -> str:
    return f"{workspace_name} — {day.strftime('%A %d/%m/%Y')}"


def render(workspace_name: str, figures: Figures) -> str:
    """The email and preview text."""
    return "\n".join([heading(workspace_name, figures.day), *lines(figures)])


def one_line(figures: Figures) -> str:
    """The summary for a WhatsApp template value, which cannot contain line breaks."""
    return " | ".join(lines(figures))
