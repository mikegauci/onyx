"""Parsing WhatsApp webhooks, rendering templates and the 24-hour rule. No database."""

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from app.modules.inbox.channels.whatsapp import (
    TemplateParamError,
    is_stop,
    parse_webhook,
    render_template,
    window_open,
)
from app.modules.inbox.models import BODY_MAX_LENGTH, WhatsAppSendStatus

NOW = datetime(2026, 11, 19, 12, 0, tzinfo=UTC)
STOP = frozenset({"stop", "unsubscribe", "ieqaf"})


def _payload(*, messages: list[Any] | None = None, statuses: list[Any] | None = None) -> Any:
    value: dict[str, Any] = {
        "messaging_product": "whatsapp",
        "metadata": {"display_phone_number": "35621000000", "phone_number_id": "111"},
        "contacts": [{"profile": {"name": "Clara Borg"}, "wa_id": "35621000001"}],
    }
    if messages is not None:
        value["messages"] = messages
    if statuses is not None:
        value["statuses"] = statuses
    return {
        "object": "whatsapp_business_account",
        "entry": [{"id": "999", "changes": [{"field": "messages", "value": value}]}],
    }


def _message(**fields: Any) -> dict[str, Any]:
    return {
        "from": "35621000001",
        "id": "wamid.1",
        "timestamp": str(int(NOW.timestamp()) - 60),
        "type": "text",
        "text": {"body": "Is the 2019 Golf still available?"},
        **fields,
    }


def _parse(payload: Any) -> Any:
    return parse_webhook(payload, now=NOW, stop_words=STOP)


def test_a_text_message_becomes_a_message_threaded_by_the_customers_number() -> None:
    [item], statuses, skipped = _parse(_payload(messages=[_message()]))
    assert (statuses, skipped) == ([], 0)
    assert item.phone_number_id == "111"
    assert item.message.body == "Is the 2019 Golf still available?"
    assert item.message.sender_phone == "+35621000001"
    assert item.message.sender_name == "Clara Borg"
    assert item.message.external_message_id == "wamid.1"
    assert item.message.external_thread_ref == "wa:+35621000001"
    assert item.message.occurred_at == NOW - timedelta(seconds=60)
    assert item.stop_requested is False


def test_media_is_a_placeholder_with_its_caption_and_reactions_are_ignored() -> None:
    image = _message(id="wamid.2", type="image", image={"id": "m1", "caption": "This one?"})
    voice = _message(id="wamid.3", type="audio", audio={"id": "m2"})
    reaction = _message(id="wamid.4", type="reaction", reaction={"emoji": "👍"})
    items, _, skipped = _parse(_payload(messages=[image, voice, reaction]))
    assert [i.message.body for i in items] == ["[Image] This one?", "[Voice message]"]
    assert skipped == 0


def test_invalid_items_are_skipped_without_failing_the_rest() -> None:
    bad = [
        _message(id=None),
        _message(**{"from": "not-a-number"}),
        _message(text={"body": "   "}),
        "junk",
    ]
    items, _, skipped = _parse(_payload(messages=[*bad, _message(id="wamid.ok")]))
    assert [i.message.external_message_id for i in items] == ["wamid.ok"]
    assert skipped == 4


def test_other_objects_and_fields_are_ignored() -> None:
    assert _parse({**_payload(messages=[_message()]), "object": "page"}) == ([], [], 0)
    payload = _payload(messages=[_message()])
    payload["entry"][0]["changes"][0]["field"] = "account_update"
    assert _parse(payload) == ([], [], 0)


def test_long_messages_are_shortened_and_future_times_are_clamped() -> None:
    long = _message(text={"body": "x" * (BODY_MAX_LENGTH + 500)})
    future = _message(id="wamid.f", timestamp=str(int(NOW.timestamp()) + 3600))
    first, second = _parse(_payload(messages=[long, future]))[0]
    assert len(first.message.body) == BODY_MAX_LENGTH
    assert first.message.body.endswith("[Message shortened]")
    assert second.message.occurred_at == NOW


@pytest.mark.parametrize(
    ("text", "stop"),
    [
        ("STOP", True),
        (" stop. ", True),
        ("Ieqaf", True),
        ("unsubscribe!", True),
        ("please stop calling", False),
        ("Stopper", False),
    ],
)
def test_stop_words_are_matched_as_the_whole_message(text: str, stop: bool) -> None:
    assert is_stop(text, STOP) is stop


def test_status_reports_carry_the_attempt_id_and_error_code_only() -> None:
    reports = [
        {
            "id": "wamid.out",
            "status": "failed",
            "biz_opaque_callback_data": "0b8c1d3e-0000-0000-0000-000000000000",
            "errors": [{"code": 131047, "title": "Re-engagement message", "message": "text"}],
        },
        {"id": "wamid.out2", "status": "read"},
        {"id": "wamid.out3", "status": "deleted"},  # not a status we track
    ]
    _, statuses, skipped = _parse(_payload(statuses=reports))
    assert skipped == 1
    failed, read = statuses
    assert failed.status is WhatsAppSendStatus.FAILED
    assert failed.detail == "131047"
    assert failed.callback_data == "0b8c1d3e-0000-0000-0000-000000000000"
    assert read.status is WhatsAppSendStatus.READ
    assert read.detail is None


def test_templates_render_with_checked_values() -> None:
    body = "Hello {{1}}, the {{2}} you asked about is in. {{1}}, reply here."
    assert render_template(body, ("Clara", "Golf"), 2) == (
        "Hello Clara, the Golf you asked about is in. Clara, reply here."
    )
    for params, index in [
        (("Clara",), None),
        (("Clara", " "), 1),
        (("Clara", "two\nlines"), 1),
        (("Clara", "a     b"), 1),
        (("x" * 1025, "Golf"), 0),
    ]:
        with pytest.raises(TemplateParamError) as caught:
            render_template(body, params, 2)
        assert caught.value.index == index


def test_the_reply_window_is_24_hours_from_the_last_customer_message() -> None:
    assert window_open(NOW - timedelta(hours=23, minutes=59), NOW)
    assert not window_open(NOW - timedelta(hours=24), NOW)
    assert not window_open(None, NOW)
