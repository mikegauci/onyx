"""Outbound draft rules without a database: transitions, expiry and quote blocks."""

from datetime import UTC, date, datetime, timedelta

import pytest

from app.modules.outbound.lifecycle import (
    EXPIRY_TEXT,
    OPEN,
    QUOTE_BLOCK_TEXT,
    DraftStatus,
    ExpiryReason,
    QuoteBlock,
    QuoteState,
    can_approve,
    can_edit,
    can_reject,
    can_send,
    expiry_reason,
    quote_block,
)

NOW = datetime(2026, 11, 6, 12, 0, tzinfo=UTC)
TODAY = date(2026, 11, 6)
APPROVED = QuoteState(status="approved", version=2, version_approved=True, valid_until=TODAY)


def _reason(**overrides: object) -> ExpiryReason | None:
    values: dict[str, object] = {
        "status": DraftStatus.PENDING,
        "now": NOW,
        "expires_at": NOW + timedelta(hours=1),
        "context_at": NOW - timedelta(hours=1),
        "latest_inbound_at": NOW - timedelta(hours=1),
        "approved_quote_version": None,
        "quote": None,
        "today": TODAY,
    } | overrides
    return expiry_reason(**values)  # type: ignore[arg-type]


def test_only_an_approved_draft_can_be_sent() -> None:
    assert [s for s in DraftStatus if can_send(s)] == [DraftStatus.APPROVED]


@pytest.mark.parametrize("check", [can_edit, can_approve, can_reject])
def test_only_open_drafts_change(check: object) -> None:
    assert {s for s in DraftStatus if check(s)} == OPEN  # type: ignore[operator]


def test_a_fresh_draft_holds() -> None:
    assert _reason() is None


def test_time_expiry_is_inclusive() -> None:
    assert _reason(expires_at=NOW) is ExpiryReason.TIME


def test_a_newer_customer_message_makes_it_stale() -> None:
    assert _reason(latest_inbound_at=NOW) is ExpiryReason.NEW_CUSTOMER_MESSAGE
    # A first customer message after a draft written without one also counts.
    assert _reason(context_at=None, latest_inbound_at=NOW) is ExpiryReason.NEW_CUSTOMER_MESSAGE
    assert _reason(context_at=None, latest_inbound_at=None) is None


def test_closed_drafts_never_expire_again() -> None:
    for status in set(DraftStatus) - OPEN:
        assert _reason(status=status, expires_at=NOW - timedelta(days=1)) is None


def test_a_pending_draft_is_blocked_not_expired_by_its_quote() -> None:
    draft_quote = QuoteState(status="draft", version=1, version_approved=False, valid_until=None)
    assert _reason(quote=draft_quote) is None
    assert quote_block(draft_quote, TODAY) is QuoteBlock.NOT_APPROVED


@pytest.mark.parametrize(
    ("quote", "expected"),
    [
        (APPROVED, None),
        (None, ExpiryReason.QUOTE_CHANGED),
        (QuoteState("approved", 3, True, TODAY), ExpiryReason.QUOTE_CHANGED),  # re-approved
        (QuoteState("draft", 3, False, None), ExpiryReason.QUOTE_CHANGED),  # being revised
        (QuoteState("cancelled", 2, True, TODAY), ExpiryReason.QUOTE_CHANGED),
        (QuoteState("accepted", 2, True, TODAY), ExpiryReason.QUOTE_CHANGED),
        (QuoteState("approved", 2, True, date(2026, 11, 5)), ExpiryReason.QUOTE_EXPIRED),
    ],
)
def test_an_approved_reply_holds_only_while_its_quote_version_does(
    quote: QuoteState | None, expected: ExpiryReason | None
) -> None:
    assert _reason(status=DraftStatus.APPROVED, approved_quote_version=2, quote=quote) is expected


def test_quote_blocks() -> None:
    assert quote_block(APPROVED, TODAY) is None
    assert quote_block(APPROVED, TODAY + timedelta(days=1)) is QuoteBlock.PAST_VALIDITY
    assert quote_block(QuoteState("accepted", 2, True, TODAY), TODAY) is QuoteBlock.NOT_APPROVED


def test_every_reason_has_text() -> None:
    assert set(EXPIRY_TEXT) == set(ExpiryReason)
    assert set(QUOTE_BLOCK_TEXT) == set(QuoteBlock)
