"""Outbound draft states and the pure rules for moving between them. No database access.

```text
pending ── edit ──▶ pending (new revision)
pending ── approve ──▶ approved ── send ──▶ sent
approved ── edit ──▶ pending (the new revision needs approval again)
pending | approved ── reject ──▶ rejected
pending | approved ── expire ──▶ expired     (time, newer customer message, quote changed)
pending | approved ── new assistant draft ──▶ superseded
```

Sent, rejected, expired and superseded are final. A trigger enforces that in the database too.
"""

import enum
from dataclasses import dataclass
from datetime import date, datetime

DEFAULT_EXPIRY_HOURS = 72
MAX_EXPIRY_HOURS = 720  # 30 days


class DraftStatus(enum.StrEnum):
    PENDING = "pending"  # waiting for an approver
    APPROVED = "approved"  # this exact revision may be sent
    SENT = "sent"
    REJECTED = "rejected"
    EXPIRED = "expired"
    SUPERSEDED = "superseded"  # a newer assistant draft replaced it


OPEN = frozenset({DraftStatus.PENDING, DraftStatus.APPROVED})


class DraftOrigin(enum.StrEnum):
    """Who wrote a draft or a revision."""

    ASSISTANT = "assistant"
    STAFF = "staff"


class ExpiryReason(enum.StrEnum):
    TIME = "time"  # older than the workspace's expiry setting
    NEW_CUSTOMER_MESSAGE = "new_customer_message"  # the customer wrote again since
    QUOTE_CHANGED = "quote_changed"  # the approved quote was revised, cancelled or decided
    QUOTE_EXPIRED = "quote_expired"  # the approved quote passed its valid-until date


EXPIRY_TEXT: dict[ExpiryReason, str] = {
    ExpiryReason.TIME: "The draft is older than the workspace allows. Draft the reply again.",
    ExpiryReason.NEW_CUSTOMER_MESSAGE: (
        "The customer wrote again after this draft. Draft a reply to the latest message."
    ),
    ExpiryReason.QUOTE_CHANGED: (
        "The quote changed after the reply was approved. Draft the reply again."
    ),
    ExpiryReason.QUOTE_EXPIRED: (
        "The quote is past its valid-until date. Revise the quote and draft the reply again."
    ),
}


class QuoteBlock(enum.StrEnum):
    """Why an attached quote stops a reply being approved (the draft stays pending)."""

    NOT_APPROVED = "quote_not_approved"
    PAST_VALIDITY = "quote_past_validity"


QUOTE_BLOCK_TEXT: dict[QuoteBlock, str] = {
    QuoteBlock.NOT_APPROVED: "Approve the quote before approving a reply that includes it.",
    QuoteBlock.PAST_VALIDITY: (
        "The quote is past its valid-until date. Revise and approve it before approving the reply."
    ),
}


@dataclass(frozen=True)
class QuoteState:
    """What the outbound rules need to know about the attached quote, read fresh."""

    status: str  # QuoteStatus value: draft, approved, accepted, declined, cancelled
    version: int  # the quote's current version number
    version_approved: bool  # the current version is approved (frozen)
    valid_until: date | None


def quote_block(quote: QuoteState, today: date) -> QuoteBlock | None:
    """Why the reply cannot be approved with this quote yet, if anything."""
    if quote.status != "approved" or not quote.version_approved:
        return QuoteBlock.NOT_APPROVED
    if quote.valid_until is None or quote.valid_until < today:
        return QuoteBlock.PAST_VALIDITY
    return None


def expiry_reason(
    *,
    status: DraftStatus,
    now: datetime,
    expires_at: datetime,
    context_at: datetime | None,
    latest_inbound_at: datetime | None,
    approved_quote_version: int | None,
    quote: QuoteState | None,
    today: date,
) -> ExpiryReason | None:
    """Why an open draft is no longer valid, or None. Closed drafts never expire again."""
    if status not in OPEN:
        return None
    if now >= expires_at:
        return ExpiryReason.TIME
    if latest_inbound_at is not None and (context_at is None or latest_inbound_at > context_at):
        return ExpiryReason.NEW_CUSTOMER_MESSAGE
    if approved_quote_version is not None:
        # Only an approved reply pins its quote version; a pending one is blocked instead.
        if (
            quote is None
            or quote.status != "approved"
            or quote.version != approved_quote_version
            or not quote.version_approved
        ):
            return ExpiryReason.QUOTE_CHANGED
        if quote.valid_until is None or quote.valid_until < today:
            return ExpiryReason.QUOTE_EXPIRED
    return None


def can_edit(status: DraftStatus) -> bool:
    return status in OPEN


def can_approve(status: DraftStatus) -> bool:
    return status in OPEN


def can_reject(status: DraftStatus) -> bool:
    return status in OPEN


def can_send(status: DraftStatus) -> bool:
    return status is DraftStatus.APPROVED
