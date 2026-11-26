"""Daily owner summary (VA-010): the day's figures, the settings and the scheduled send.

The figures are read in a tenant-bound transaction, so RLS scopes every query, and each query
also filters by ``organization_id``. A module that is off gives a missing section, not zero.

Sending happens in two steps so a day is sent at most once: the day's row is claimed first
(unique per workspace and local date) and committed with status ``sending``; then each recipient
is sent and the row records what happened. A crash between the two leaves the row ``sending``
and nothing is sent again. The summary goes to the workspace's own members, never to customers,
so it does not wait for staff approval.
"""

import logging
import re
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db.context import TenantContext, worker_transaction
from app.core.db.rls import WORKER_ROLE
from app.core.insights import daily
from app.core.insights import service as insights
from app.core.insights.models import OwnerSummary, OwnerSummarySettings
from app.modules.inbox import public as inbox

logger = logging.getLogger("onyx.insights.summary")

MAX_RECIPIENTS = 5
PARAM_KEYS = ("workspace", "date", "summary")
E164 = re.compile(r"^\+[1-9]\d{6,14}$")
HISTORY_DAYS = 30


@dataclass(frozen=True)
class Member:
    user_id: uuid.UUID
    display_name: str
    email: str


async def _enabled(db: AsyncSession, org: uuid.UUID, module: str) -> bool:
    return bool(
        await db.scalar(text("SELECT app_module_enabled(:org, :m)"), {"org": org, "m": module})
    )


async def _row(db: AsyncSession, sql: str, p: dict[str, Any]) -> Any:
    return (await db.execute(text(sql), p)).mappings().one()


async def collect(db: AsyncSession, org: uuid.UUID, day: date, zone: ZoneInfo) -> daily.Figures:
    """The figures for the local ``day`` (so far, if it is today)."""
    start, end = daily.day_bounds(day, zone)
    p = {"org": org, "since": start, "until": end}
    missing: dict[str, daily.Missing] = {"social": daily.Missing.NOT_CONNECTED}
    enquiries = deals = payments = listings = None

    if not await _enabled(db, org, "inbox"):
        missing["enquiries"] = daily.Missing.NOT_SET_UP
    elif not await db.scalar(
        text(
            "SELECT EXISTS (SELECT 1 FROM inbox_channels WHERE organization_id = :org "
            "AND disabled_at IS NULL)"
        ),
        p,
    ):
        missing["enquiries"] = daily.Missing.NOT_CONNECTED
    else:
        found = await insights.enquiries(db, p)
        missed = await db.scalar(
            text(
                "SELECT count(*) FROM inbox_missed_calls WHERE organization_id = :org "
                "AND created_at >= :since AND created_at < :until"
            ),
            p,
        )
        enquiries = daily.Enquiries(found.total, found.by_channel, int(missed or 0))

    if await _enabled(db, org, "deals"):
        row = await _row(
            db,
            """
            SELECT
              (SELECT count(*) FROM deal_events WHERE organization_id = :org
                 AND kind = 'created' AND occurred_at >= :since AND occurred_at < :until)
                AS reserved,
              (SELECT count(*) FROM deals WHERE organization_id = :org
                 AND sold_at >= :since AND sold_at < :until) AS sold,
              (SELECT count(*) FROM finance_payments WHERE organization_id = :org
                 AND voided_at IS NULL AND created_at >= :since AND created_at < :until)
                AS payments,
              (SELECT coalesce(sum(amount_cents), 0) FROM finance_payments
                 WHERE organization_id = :org AND voided_at IS NULL
                   AND created_at >= :since AND created_at < :until) AS paid_cents
            """,
            p,
        )
        deals = daily.Deals(int(row["reserved"]), int(row["sold"]))
        payments = daily.Payments(int(row["payments"]), int(row["paid_cents"]))
    else:
        missing["deals"] = missing["payments"] = daily.Missing.NOT_SET_UP

    if await _enabled(db, org, "automotive"):
        row = await _row(
            db,
            """
            SELECT
              (SELECT count(*) FROM automotive_vehicle_events e
                 WHERE e.organization_id = :org AND e.occurred_at >= :since
                   AND e.occurred_at < :until
                   AND e.to_status IN ('available', 'reserved')
                   AND (e.from_status IS NULL OR e.from_status IN ('sold', 'withdrawn')))
                AS added,
              (SELECT count(*) FROM automotive_vehicle_events e
                 WHERE e.organization_id = :org AND e.occurred_at >= :since
                   AND e.occurred_at < :until
                   AND e.to_status IN ('sold', 'withdrawn')
                   AND e.from_status IN ('available', 'reserved')) AS removed,
              (SELECT count(*) FROM automotive_vehicles WHERE organization_id = :org
                 AND status = 'available') AS available
            """,
            p,
        )
        listings = daily.Listings(int(row["added"]), int(row["removed"]), int(row["available"]))
    else:
        missing["listings"] = daily.Missing.NOT_SET_UP

    return daily.Figures(
        day=day,
        enquiries=enquiries,
        deals=deals,
        payments=payments,
        listings=listings,
        missing=missing,
    )


async def members(db: AsyncSession) -> list[Member]:
    rows = await db.execute(text("SELECT user_id, display_name, email FROM app_summary_members()"))
    return [Member(r.user_id, r.display_name, r.email) for r in rows]


async def load_settings(db: AsyncSession, org: uuid.UUID) -> OwnerSummarySettings:
    found = await db.get(OwnerSummarySettings, org, populate_existing=True)
    return found or OwnerSummarySettings(
        organization_id=org, enabled=False, send_at=time(19, 0), recipients=[], params=[]
    )


async def save_settings(
    db: AsyncSession, org: uuid.UUID, user_id: uuid.UUID, values: dict[str, Any]
) -> None:
    await db.execute(
        insert(OwnerSummarySettings)
        .values(organization_id=org, updated_by_user_id=user_id, **values)
        .on_conflict_do_update(
            index_elements=[OwnerSummarySettings.organization_id],
            set_={**values, "updated_by_user_id": user_id, "updated_at": text("now()")},
        )
    )


def _params(keys: list[str], name: str, figures: daily.Figures) -> list[str]:
    values = {
        "workspace": name,
        "date": figures.day.strftime("%d/%m/%Y"),
        "summary": daily.one_line(figures),
    }
    return [values[k] for k in keys]


async def send_all(
    db: AsyncSession,
    tenant: TenantContext,
    *,
    settings: OwnerSummarySettings,
    recipients: list[dict[str, Any]],
    name: str,
    figures: daily.Figures,
    key: str,
) -> list[dict[str, Any]]:
    """Send the summary to each recipient and channel; one failure never stops the others."""
    by_id = {str(m.user_id): m for m in await members(db)}
    body = daily.render(name, figures)
    subject = f"Daily summary — {figures.day.strftime('%A %d/%m/%Y')}"
    results: list[dict[str, Any]] = []
    for recipient in recipients:
        user = str(recipient.get("user_id"))
        member = by_id.get(user)
        channels: list[str] = (["email"] if recipient.get("email") else []) + (
            ["whatsapp"] if recipient.get("whatsapp") else []
        )
        for channel in channels:
            result: dict[str, Any] = {"user_id": user, "channel": channel}
            try:
                if member is None:
                    raise inbox.StaffSendError("not_a_member")
                if channel == "email":
                    await inbox.send_staff_email(
                        from_name=name,
                        to=member.email,
                        subject=subject,
                        text=body,
                        idempotency_key=f"{key}:{user}:email",
                        tags={"organization": tenant.organization_id.hex, "kind": "summary"},
                    )
                else:
                    if settings.template_id is None:
                        raise inbox.StaffSendError("no_template")
                    await inbox.send_staff_whatsapp(
                        db,
                        tenant,
                        template_id=settings.template_id,
                        to=str(recipient["whatsapp"]),
                        params=_params(list(settings.params), name, figures),
                        callback_data=f"summary:{key}"[:64],
                    )
                result |= {"status": "sent", "reason": None}
            except inbox.StaffSendError as exc:
                result |= {"status": "skipped" if exc.reason == "no_template" else "failed"}
                result["reason"] = exc.reason
            results.append(result)
    return results


def outcome(results: list[dict[str, Any]]) -> str:
    sent = sum(r["status"] == "sent" for r in results)
    if results and sent == len(results):
        return "sent"
    return "partly_sent" if sent else "failed"


async def tenants(sessions: Any) -> list[uuid.UUID]:
    async with sessions() as session, session.begin():
        await session.execute(text(f"SET LOCAL ROLE {WORKER_ROLE}"))
        rows = await session.execute(
            text("SELECT organization_id FROM scheduler_summary_tenants()")
        )
        return list(rows.scalars().all())


async def run_due(sessions: Any, org: uuid.UUID, now: datetime) -> bool:
    """Send today's summary for ``org`` if it is due and not sent yet. True when it was sent."""
    async with worker_transaction(sessions, org) as (db, _tenant):
        settings = await db.get(OwnerSummarySettings, org)
        if settings is None or not settings.enabled or not settings.recipients:
            return False
        workspace = (
            await db.execute(
                text("SELECT name, timezone FROM organizations WHERE id = :org"), {"org": org}
            )
        ).one()
        zone = daily.zone_of(workspace.timezone)
        day = daily.due_date(now, zone, settings.send_at)
        if day is None:
            return False
        figures = await collect(db, org, day, zone)
        claimed = await db.scalar(
            insert(OwnerSummary)
            .values(
                organization_id=org,
                summary_date=day,
                figures=figures.to_json(),
                body=daily.render(workspace.name, figures),
                status="sending",
            )
            .on_conflict_do_nothing(constraint="uq_owner_summaries_organization_date")
            .returning(OwnerSummary.id)
        )
        if claimed is None:
            return False
    async with worker_transaction(sessions, org) as (db, tenant):
        settings = await load_settings(db, org)
        results = await send_all(
            db,
            tenant,
            settings=settings,
            recipients=list(settings.recipients),
            name=workspace.name,
            figures=figures,
            key=f"summary:{org.hex}:{day.isoformat()}",
        )
        row = await db.get(OwnerSummary, claimed)
        assert row is not None  # noqa: S101 - claimed in the transaction above
        row.status = outcome(results)
        row.results = results
        row.sent_at = datetime.now(UTC)
    logger.info(
        "owner summary",
        extra={"organization_id": str(org), "status": row.status, "sends": len(results)},
    )
    return True


async def history(db: AsyncSession, org: uuid.UUID) -> list[OwnerSummary]:
    rows = await db.scalars(
        select(OwnerSummary)
        .where(OwnerSummary.organization_id == org)
        .order_by(OwnerSummary.summary_date.desc())
        .limit(HISTORY_DAYS)
    )
    return list(rows.all())
