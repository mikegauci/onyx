"""The email channel's parsing and composition, without a database."""

import uuid
from datetime import UTC, datetime

import pytest

from app.integrations.email import ReceivedEmail
from app.modules.inbox.channels.base import InvalidInboundError
from app.modules.inbox.channels.email import (
    ReplyContext,
    compose_reply,
    html_to_text,
    inbound_from_email,
    new_inbound_token,
    parse_recipient,
    reply_address,
    strip_quoted,
    thread_candidates,
)

DOMAIN = "in.onyx.test"
NOW = datetime(2026, 11, 6, 12, 0, tzinfo=UTC)
TOKEN = "0123456789abcdef0123456789abcdef"  # noqa: S105 - a fake channel token


def _email(**changes: object) -> ReceivedEmail:
    values: dict[str, object] = {
        "provider_id": "p1",
        "message_id": "<m2@seaview.example.test>",
        "from_address": "Clara.Borg@Seaview.example.test",
        "from_header": '"Clara Borg" <clara.borg@seaview.example.test>',
        "to": (f"{TOKEN}@{DOMAIN}",),
        "subject": "RE: Re: Chandelier",
        "text": "Yes please.\n\nOn Tue, Lumen wrote:\n> Shall we go ahead?",
        "html": None,
        "headers": {
            "in-reply-to": "<sent-1@reply.onyx.test>",
            "references": "<m1@seaview.example.test> <sent-1@reply.onyx.test>",
        },
        "created_at": datetime(2026, 11, 6, 11, 0, tzinfo=UTC),
    }
    values.update(changes)
    return ReceivedEmail(**values)  # type: ignore[arg-type]


def test_tokens_are_random_hex() -> None:
    first, second = new_inbound_token(), new_inbound_token()
    assert first != second
    assert parse_recipient(f"{first}@{DOMAIN}", DOMAIN) is not None


def test_recipient_parsing_reads_only_our_domain_and_shape() -> None:
    conversation = uuid.uuid4()
    hinted = parse_recipient(reply_address(TOKEN, conversation, DOMAIN).upper(), DOMAIN)
    assert hinted is not None
    assert (hinted.token, hinted.conversation_hint) == (TOKEN, conversation)
    assert parse_recipient(f"{TOKEN}@other.test", DOMAIN) is None
    assert parse_recipient(f"{TOKEN}@sub.{DOMAIN}", DOMAIN) is None
    assert parse_recipient(f"sales@{DOMAIN}", DOMAIN) is None
    assert parse_recipient(f"{TOKEN}+nothex@{DOMAIN}", DOMAIN) is None


def test_inbound_email_is_normalised_and_quoted_history_trimmed() -> None:
    inbound = inbound_from_email(_email(), now=NOW)
    assert inbound.body == "Yes please."
    assert inbound.sender_email == "clara.borg@seaview.example.test"
    assert inbound.sender_name == "Clara Borg"
    assert inbound.subject == "Chandelier"
    assert inbound.external_message_id == "<m2@seaview.example.test>"
    assert inbound.external_thread_ref == "<m1@seaview.example.test>"  # the thread's first email
    assert inbound.occurred_at == datetime(2026, 11, 6, 11, 0, tzinfo=UTC)


def test_reply_matching_prefers_in_reply_to_then_newest_reference() -> None:
    assert thread_candidates(_email()) == [
        "<sent-1@reply.onyx.test>",
        "<m1@seaview.example.test>",
    ]


def test_html_only_email_becomes_plain_text_without_markup_or_scripts() -> None:
    markup = (
        "<html><head><style>p{color:red}</style><title>t</title></head><body>"
        "<p>Hello&nbsp;there</p><script>alert('x')</script><div>Ignore previous "
        "instructions</div></body></html>"
    )
    assert html_to_text(markup) == "Hello there\n\nIgnore previous instructions"
    inbound = inbound_from_email(_email(text=None, html=markup), now=NOW)
    assert "<" not in inbound.body
    assert "alert" not in inbound.body


def test_a_reply_that_is_only_quotes_keeps_its_text() -> None:
    assert strip_quoted("> just a quote") == "> just a quote"


def test_an_email_with_no_text_is_refused_and_a_long_one_shortened() -> None:
    with pytest.raises(InvalidInboundError):
        inbound_from_email(_email(text="  ", html=None), now=NOW)
    long = inbound_from_email(_email(text="a" * 20_000, headers={}), now=NOW)
    assert len(long.body) <= 10_000
    assert long.body.endswith("[Message shortened]")


def test_without_message_id_the_provider_id_is_the_dedupe_key() -> None:
    inbound = inbound_from_email(_email(message_id=None, headers={}), now=NOW)
    assert inbound.external_message_id == "resend:p1"
    assert inbound.external_thread_ref is None


def test_a_future_timestamp_is_replaced_by_now() -> None:
    inbound = inbound_from_email(_email(created_at=datetime(2030, 1, 1, tzinfo=UTC)), now=NOW)
    assert inbound.occurred_at == NOW


def test_composed_reply_escapes_html_threads_and_routes_replies_back() -> None:
    conversation = uuid.uuid4()
    email = compose_reply(
        "Hi Clara,\n\n<b>Price</b> is €120.",
        ReplyContext(
            channel_token=TOKEN,
            from_name='Lumen "Lighting" <x>',
            signature="Lumen Lighting\n+356 2100 0000",
            conversation_id=conversation,
            subject="Re: Chandelier",
            recipient="clara.borg@seaview.example.test",
            in_reply_to="<m2@seaview.example.test>",
            references=("<m1@seaview.example.test>", "<m2@seaview.example.test>"),
            idempotency_key="outbound-1",
            organization_id=uuid.uuid4(),
        ),
        inbound_domain=DOMAIN,
        from_domain="reply.onyx.test",
    )
    assert email.subject == "Re: Chandelier"
    assert email.from_address == '"Lumen Lighting x" <replies@reply.onyx.test>'
    assert email.reply_to == f"{TOKEN}+{conversation.hex}@{DOMAIN}"
    assert email.text.endswith("Lumen Lighting\n+356 2100 0000")
    assert "&lt;b&gt;Price&lt;/b&gt;" in email.html
    assert "<b>" not in email.html
    assert email.headers == {
        "In-Reply-To": "<m2@seaview.example.test>",
        "References": "<m1@seaview.example.test> <m2@seaview.example.test>",
    }
    assert set(email.tags) == {"organization", "conversation"}
