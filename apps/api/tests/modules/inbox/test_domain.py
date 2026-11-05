"""Inbox domain rules without a database: lifecycle, handoff policy and the channel contract."""

import asyncio
import itertools
from datetime import UTC, datetime, timedelta

import pytest

from app.modules.inbox.channels.base import (
    ADAPTERS,
    ChannelNotConnectedError,
    InvalidInboundError,
    ManualChannelAdapter,
    OutboundMessage,
    adapter_for,
    normalise_inbound,
)
from app.modules.inbox.lifecycle import (
    INITIAL_HANDLER,
    STATUS_AFTER_INBOUND,
    TRANSITIONS,
    allowed_transitions,
    can_post,
    can_transition,
    handoff_needs_manager,
)
from app.modules.inbox.models import (
    BODY_MAX_LENGTH,
    ChannelKind,
    ConversationStatus,
    DeliveryStatus,
    Handler,
    MessageDirection,
)

OPEN, WAITING, CLOSED = (
    ConversationStatus.OPEN,
    ConversationStatus.WAITING_ON_CUSTOMER,
    ConversationStatus.CLOSED,
)
NOW = datetime(2026, 11, 5, 12, 0, tzinfo=UTC)

# --- lifecycle -------------------------------------------------------------------------------


def test_every_status_has_transitions() -> None:
    assert set(TRANSITIONS) == set(ConversationStatus)


@pytest.mark.parametrize(
    ("current", "target", "allowed"),
    [
        (OPEN, WAITING, True),
        (OPEN, CLOSED, True),
        (WAITING, OPEN, True),
        (WAITING, CLOSED, True),
        (CLOSED, OPEN, True),
        (CLOSED, WAITING, False),
    ],
)
def test_status_transitions(
    current: ConversationStatus, target: ConversationStatus, allowed: bool
) -> None:
    assert can_transition(current, target) is allowed


@pytest.mark.parametrize("status", list(ConversationStatus))
def test_no_status_transitions_to_itself(status: ConversationStatus) -> None:
    assert status not in allowed_transitions(status)


def test_customer_messages_reopen_and_new_conversations_go_to_staff() -> None:
    assert STATUS_AFTER_INBOUND is OPEN
    assert INITIAL_HANDLER is Handler.STAFF


@pytest.mark.parametrize(
    ("status", "direction"), list(itertools.product(ConversationStatus, MessageDirection))
)
def test_only_replies_to_closed_conversations_are_refused(
    status: ConversationStatus, direction: MessageDirection
) -> None:
    refused = status is CLOSED and direction is MessageDirection.OUTBOUND
    assert can_post(status, direction) is not refused


def test_handing_to_the_assistant_needs_a_manager_but_taking_back_does_not() -> None:
    assert handoff_needs_manager(Handler.ASSISTANT) is True
    assert handoff_needs_manager(Handler.STAFF) is False


# --- channel contract ------------------------------------------------------------------------


def test_only_the_manual_channel_is_connected() -> None:
    assert set(ADAPTERS) == {ChannelKind.MANUAL}
    assert adapter_for(ChannelKind.MANUAL).kind is ChannelKind.MANUAL
    for kind in (ChannelKind.EMAIL, ChannelKind.WHATSAPP, ChannelKind.WEB):
        with pytest.raises(ChannelNotConnectedError):
            adapter_for(kind)


def test_inbound_is_normalised() -> None:
    message = normalise_inbound(
        {
            "body": "  Do you have the arc pendant in brass?  ",
            "sender_name": " Anna ",
            "sender_email": " Anna@Example.TEST ",
            "sender_phone": "2123 4567",
            "occurred_at": "2026-11-05T13:00:00+02:00",
            "external_message_id": " msg-1 ",
            "external_thread_ref": "thread-9",
        },
        now=NOW,
    )
    assert message.body == "Do you have the arc pendant in brass?"
    assert (message.sender_name, message.sender_email, message.sender_phone) == (
        "Anna",
        "anna@example.test",
        "+35621234567",
    )
    assert message.sender_address == "anna@example.test"  # email preferred
    assert message.occurred_at == datetime(2026, 11, 5, 11, 0, tzinfo=UTC)
    assert (message.external_message_id, message.external_thread_ref) == ("msg-1", "thread-9")


def test_inbound_time_defaults_to_now() -> None:
    assert normalise_inbound({"body": "Hi"}, now=NOW).occurred_at == NOW


@pytest.mark.parametrize(
    ("payload", "field"),
    [
        ({"body": "   "}, "body"),
        ({}, "body"),
        ({"body": "x" * (BODY_MAX_LENGTH + 1)}, "body"),
        ({"body": "Hi", "sender_email": "not-an-email"}, "sender_email"),
        ({"body": "Hi", "sender_phone": "12"}, "sender_phone"),
        ({"body": "Hi", "occurred_at": "yesterday"}, "occurred_at"),
        ({"body": "Hi", "occurred_at": "2026-11-05T12:00:00"}, "occurred_at"),
        (
            {"body": "Hi", "occurred_at": (NOW + timedelta(hours=1)).isoformat()},
            "occurred_at",
        ),
        ({"body": "Hi", "external_message_id": "x" * 256}, "external_message_id"),
        ({"body": "Hi", "sender_name": 42}, "sender_name"),
    ],
)
def test_invalid_inbound_names_the_field_without_echoing_values(
    payload: dict[str, object], field: str
) -> None:
    with pytest.raises(InvalidInboundError) as exc:
        normalise_inbound(payload, now=NOW)
    assert exc.value.field == field
    assert "not-an-email" not in str(exc.value)


def test_manual_adapter_ignores_thread_refs_and_sends_nothing() -> None:
    adapter = ManualChannelAdapter()
    inbound = adapter.parse_inbound({"body": "Hi", "external_thread_ref": "forged"}, now=NOW)
    assert inbound.external_thread_ref is None
    result = asyncio.run(adapter.send(OutboundMessage(body="Reply", recipient_address=None)))
    assert result.status is DeliveryStatus.LOGGED
    assert result.external_message_id is None
