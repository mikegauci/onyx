"""Insights for one workspace over the last N days.

Every query runs in the request's tenant-bound transaction, so RLS scopes it, and each one also
filters by ``organization_id``. Module tables are only read when the module is enabled; a
disabled module's section is ``None``. Figures are counts, durations in seconds and reason
codes: never message text.
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

ALLOWED_DAYS = (7, 30, 90)
TOP_REASONS = 5


@dataclass(frozen=True)
class Enquiries:
    total: int
    by_channel: dict[str, int]


@dataclass(frozen=True)
class ResponseTime:
    answered: int  # conversations with a customer message and a reply by a person
    unanswered: int  # with a customer message and no reply by a person yet
    median_seconds: int | None
    p90_seconds: int | None
    automatic_replies: int  # system messages such as missed-call text-back (not in the median)


@dataclass(frozen=True)
class Drafts:
    total: int
    sent_as_written: int
    sent_after_edit: int
    rejected: int
    expired: int
    waiting: int  # pending or approved, not sent yet
    superseded: int
    median_approval_seconds: int | None


@dataclass(frozen=True)
class Runs:
    total: int
    drafted: int
    escalated: int
    top_reasons: list[tuple[str, int]] = field(default_factory=list)


@dataclass(frozen=True)
class Quotes:
    created: int
    approved: int  # approved, accepted or declined: the quote was approved at some point
    sent: int  # included in a reply that was sent
    accepted: int


@dataclass(frozen=True)
class MissedCalls:
    total: int
    whatsapp_sent: int
    sms_sent: int
    skipped: int
    failed: int
    skip_reasons: list[tuple[str, int]] = field(default_factory=list)


@dataclass(frozen=True)
class Deals:
    created: int
    sold: int  # marked sold in the period
    collected: int
    cancelled: int
    open_now: int  # not sold, collected or cancelled, today
    customer_uploads: int  # documents customers sent through the upload link


@dataclass(frozen=True)
class Insights:
    days: int
    since: datetime
    enquiries: Enquiries | None
    response_time: ResponseTime | None
    drafts: Drafts | None
    runs: Runs | None
    quotes: Quotes | None
    missed_calls: MissedCalls | None
    deals: Deals | None = None


async def _one(db: AsyncSession, sql: str, params: dict[str, Any]) -> Any:
    return (await db.execute(text(sql), params)).mappings().one()


async def _pairs(db: AsyncSession, sql: str, params: dict[str, Any]) -> list[tuple[str, int]]:
    return [(str(k), int(v)) for k, v in (await db.execute(text(sql), params)).all()]


def _seconds(value: Any) -> int | None:
    return None if value is None else round(float(value))


async def enquiries(db: AsyncSession, p: dict[str, Any]) -> Enquiries:
    rows = await _pairs(
        db,
        """
        SELECT ch.kind, count(*) FROM inbox_conversations c
        JOIN inbox_channels ch
          ON ch.organization_id = c.organization_id AND ch.id = c.channel_id
        WHERE c.organization_id = :org AND c.created_at >= :since
        GROUP BY ch.kind ORDER BY ch.kind
        """,
        p,
    )
    return Enquiries(total=sum(n for _, n in rows), by_channel=dict(rows))


async def response_time(db: AsyncSession, p: dict[str, Any]) -> ResponseTime:
    row = await _one(
        db,
        """
        WITH firsts AS (
            SELECT c.id,
                   (SELECT min(m.occurred_at) FROM inbox_messages m
                     WHERE m.organization_id = c.organization_id AND m.conversation_id = c.id
                       AND m.direction = 'inbound') AS asked
            FROM inbox_conversations c
            WHERE c.organization_id = :org AND c.created_at >= :since
        ), replies AS (
            SELECT f.id,
                   (SELECT min(m.occurred_at) FROM inbox_messages m
                     WHERE m.organization_id = :org AND m.conversation_id = f.id
                       AND m.direction = 'outbound' AND m.author_kind <> 'system'
                       AND m.occurred_at >= f.asked) AS replied,
                   f.asked
            FROM firsts f WHERE f.asked IS NOT NULL
        )
        SELECT
            count(*) FILTER (WHERE replied IS NOT NULL) AS answered,
            count(*) FILTER (WHERE replied IS NULL) AS unanswered,
            percentile_cont(0.5) WITHIN GROUP (
                ORDER BY extract(epoch FROM replied - asked)
            ) FILTER (WHERE replied IS NOT NULL) AS median,
            percentile_cont(0.9) WITHIN GROUP (
                ORDER BY extract(epoch FROM replied - asked)
            ) FILTER (WHERE replied IS NOT NULL) AS p90,
            (SELECT count(*) FROM inbox_messages m
              WHERE m.organization_id = :org AND m.direction = 'outbound'
                AND m.author_kind = 'system' AND m.occurred_at >= :since) AS automatic
        FROM replies
        """,
        p,
    )
    return ResponseTime(
        answered=int(row["answered"]),
        unanswered=int(row["unanswered"]),
        median_seconds=_seconds(row["median"]),
        p90_seconds=_seconds(row["p90"]),
        automatic_replies=int(row["automatic"]),
    )


async def drafts(db: AsyncSession, p: dict[str, Any]) -> Drafts:
    row = await _one(
        db,
        """
        SELECT
            count(*) AS total,
            count(*) FILTER (WHERE d.status = 'sent' AND NOT edited) AS as_written,
            count(*) FILTER (WHERE d.status = 'sent' AND edited) AS after_edit,
            count(*) FILTER (WHERE d.status = 'rejected') AS rejected,
            count(*) FILTER (WHERE d.status = 'expired') AS expired,
            count(*) FILTER (WHERE d.status IN ('pending', 'approved')) AS waiting,
            count(*) FILTER (WHERE d.status = 'superseded') AS superseded,
            percentile_cont(0.5) WITHIN GROUP (
                ORDER BY extract(epoch FROM d.approved_at - d.created_at)
            ) FILTER (WHERE d.approved_at IS NOT NULL) AS approval
        FROM (
            SELECT d.*, EXISTS (
                SELECT 1 FROM outbound_revisions r
                 WHERE r.organization_id = d.organization_id AND r.draft_id = d.id
                   AND r.author_kind = 'staff'
            ) AS edited
            FROM outbound_drafts d
            WHERE d.organization_id = :org AND d.origin = 'assistant' AND d.created_at >= :since
        ) d
        """,
        p,
    )
    return Drafts(
        total=int(row["total"]),
        sent_as_written=int(row["as_written"]),
        sent_after_edit=int(row["after_edit"]),
        rejected=int(row["rejected"]),
        expired=int(row["expired"]),
        waiting=int(row["waiting"]),
        superseded=int(row["superseded"]),
        median_approval_seconds=_seconds(row["approval"]),
    )


async def runs(db: AsyncSession, p: dict[str, Any]) -> Runs:
    row = await _one(
        db,
        """
        SELECT count(*) AS total,
               count(*) FILTER (WHERE outcome = 'drafted') AS drafted,
               count(*) FILTER (WHERE outcome = 'escalated') AS escalated
        FROM assistant_runs WHERE organization_id = :org AND created_at >= :since
        """,
        p,
    )
    reasons = await _pairs(
        db,
        """
        SELECT reason, count(*) FROM assistant_runs r,
               jsonb_array_elements_text(r.reasons) AS reason
        WHERE r.organization_id = :org AND r.created_at >= :since AND r.outcome = 'escalated'
        GROUP BY reason ORDER BY count(*) DESC, reason LIMIT :top
        """,
        {**p, "top": TOP_REASONS},
    )
    return Runs(
        total=int(row["total"]),
        drafted=int(row["drafted"]),
        escalated=int(row["escalated"]),
        top_reasons=reasons,
    )


async def quotes(db: AsyncSession, p: dict[str, Any], *, outbound: bool) -> Quotes:
    sent = (
        """
        (SELECT count(DISTINCT d.quote_id) FROM outbound_drafts d
          WHERE d.organization_id = :org AND d.status = 'sent' AND d.quote_id IS NOT NULL
            AND d.quote_id IN (SELECT id FROM quotations_quotes q2
                                WHERE q2.organization_id = :org AND q2.created_at >= :since))
        """
        if outbound
        else "0"
    )
    row = await _one(
        db,
        f"""
        SELECT count(*) AS created,
               count(*) FILTER (WHERE status IN ('approved', 'accepted', 'declined')) AS approved,
               count(*) FILTER (WHERE status = 'accepted') AS accepted,
               {sent} AS sent
        FROM quotations_quotes WHERE organization_id = :org AND created_at >= :since
        """,  # noqa: S608 - the only interpolation is one of two fixed strings
        p,
    )
    return Quotes(
        created=int(row["created"]),
        approved=int(row["approved"]),
        sent=int(row["sent"]),
        accepted=int(row["accepted"]),
    )


async def missed_calls(db: AsyncSession, p: dict[str, Any]) -> MissedCalls:
    row = await _one(
        db,
        """
        SELECT count(*) AS total,
               count(*) FILTER (WHERE outcome = 'whatsapp_sent') AS whatsapp,
               count(*) FILTER (WHERE outcome = 'sms_sent') AS sms,
               count(*) FILTER (WHERE outcome = 'skipped') AS skipped,
               count(*) FILTER (WHERE outcome = 'failed') AS failed
        FROM inbox_missed_calls WHERE organization_id = :org AND occurred_at >= :since
        """,
        p,
    )
    reasons = await _pairs(
        db,
        """
        SELECT skip_reason, count(*) FROM inbox_missed_calls
        WHERE organization_id = :org AND occurred_at >= :since AND outcome = 'skipped'
          AND skip_reason IS NOT NULL
        GROUP BY skip_reason ORDER BY count(*) DESC, skip_reason
        """,
        p,
    )
    return MissedCalls(
        total=int(row["total"]),
        whatsapp_sent=int(row["whatsapp"]),
        sms_sent=int(row["sms"]),
        skipped=int(row["skipped"]),
        failed=int(row["failed"]),
        skip_reasons=reasons,
    )


async def deals(db: AsyncSession, p: dict[str, Any]) -> Deals:
    row = await _one(
        db,
        """
        SELECT
            count(*) FILTER (WHERE created_at >= :since) AS created,
            count(*) FILTER (WHERE sold_at >= :since) AS sold,
            count(*) FILTER (WHERE stage = 'collected' AND closed_at >= :since) AS collected,
            count(*) FILTER (WHERE stage = 'cancelled' AND closed_at >= :since) AS cancelled,
            count(*) FILTER (
                WHERE stage NOT IN ('sold', 'collected', 'cancelled')
            ) AS open_now,
            (SELECT count(*) FROM deal_documents d
              WHERE d.organization_id = :org AND d.received_from = 'customer'
                AND d.received_at >= :since) AS uploads
        FROM deals WHERE organization_id = :org
        """,
        p,
    )
    return Deals(
        created=int(row["created"]),
        sold=int(row["sold"]),
        collected=int(row["collected"]),
        cancelled=int(row["cancelled"]),
        open_now=int(row["open_now"]),
        customer_uploads=int(row["uploads"]),
    )


async def build(
    db: AsyncSession,
    organization_id: uuid.UUID,
    *,
    days: int,
    now: datetime,
    modules: frozenset[str],
) -> Insights:
    since = now - timedelta(days=days)
    p = {"org": organization_id, "since": since}
    inbox_on = "inbox" in modules
    return Insights(
        days=days,
        since=since,
        enquiries=await enquiries(db, p) if inbox_on else None,
        response_time=await response_time(db, p) if inbox_on else None,
        drafts=await drafts(db, p) if "outbound" in modules else None,
        runs=await runs(db, p) if "assistant" in modules else None,
        quotes=(
            await quotes(db, p, outbound="outbound" in modules) if "quotations" in modules else None
        ),
        missed_calls=await missed_calls(db, p) if inbox_on else None,
        deals=await deals(db, p) if "deals" in modules else None,
    )
