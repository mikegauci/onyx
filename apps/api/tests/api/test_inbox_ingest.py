"""Ingest as a channel connector will use it: threading, deduplication and contact matching.

These run against the database as the application role, bound to one tenant, exactly as a
request does. A fake provider payload is normalised with the shared channel contract.
"""

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.db.context import TenantContext, bind_tenant, identity_transaction
from app.core.db.seed import seed_auth_subject, seed_id
from app.modules.inbox.channels.base import normalise_inbound
from app.modules.inbox.ingest import ChannelDisabledError, InboxIngest, IngestResult
from app.modules.inbox.models import Channel, Conversation, ConversationStatus, Message
from tests.rls_helpers import HARBOUR, HUGO, LUMEN, OLIVIA

pytestmark = pytest.mark.anyio

SLUG = "lumen-lighting-test"
EMAIL_CHANNEL = seed_id(f"{SLUG}:channel:Shop email")
LUCA = seed_id(f"{SLUG}:contact:luca.vella@example.test")
NOW = datetime(2026, 11, 5, 12, 0, tzinfo=UTC)


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
async def sessions(db_url: str) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(db_url)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


async def _ingest(
    sessions: async_sessionmaker[AsyncSession],
    payload: dict[str, Any],
    *,
    email: str = OLIVIA,
    org: uuid.UUID = LUMEN,
    channel_id: uuid.UUID = EMAIL_CHANNEL,
) -> IngestResult:
    async with identity_transaction(sessions, seed_auth_subject(email)) as db:
        tenant: TenantContext = await bind_tenant(db, org)
        channel = await db.scalar(
            select(Channel).where(Channel.organization_id == org, Channel.id == channel_id)
        )
        assert channel is not None
        inbound = normalise_inbound(payload, now=NOW)
        return await InboxIngest(db, tenant, actor_user_id=None).ingest(channel, inbound)


async def _count(sessions: async_sessionmaker[AsyncSession], model: Any) -> int:
    async with identity_transaction(sessions, seed_auth_subject(OLIVIA)) as db:
        await bind_tenant(db, LUMEN)
        return int(await db.scalar(select(func.count()).select_from(model)) or 0)


async def test_messages_join_their_thread_and_match_the_contact(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    first = await _ingest(
        sessions,
        {
            "body": "Do you deliver to Gozo?",
            "subject": "Delivery",
            "sender_email": "Luca.Vella@example.test",
            "external_message_id": "m-1",
            "external_thread_ref": "t-1",
            "occurred_at": (NOW - timedelta(hours=2)).isoformat(),
        },
    )
    assert first.created_conversation
    assert not first.duplicate
    assert first.conversation.contact_id == LUCA
    assert first.conversation.subject == "Delivery"

    second = await _ingest(
        sessions,
        {
            "body": "And how long does it take?",
            "sender_email": "luca.vella@example.test",
            "external_message_id": "m-2",
            "external_thread_ref": "t-1",
        },
    )
    assert second.conversation.id == first.conversation.id
    assert not second.created_conversation
    assert second.message.participant_id == first.message.participant_id
    assert second.conversation.last_message_at == NOW

    other = await _ingest(
        sessions, {"body": "New topic", "external_message_id": "m-3", "external_thread_ref": "t-2"}
    )
    assert other.conversation.id != first.conversation.id
    assert other.conversation.subject == "New topic"  # falls back to the message start
    assert other.message.participant_id is None  # no sender details at all


async def test_redelivery_is_a_no_op(sessions: async_sessionmaker[AsyncSession]) -> None:
    payload = {"body": "Hello", "external_message_id": "dup-1", "external_thread_ref": "t-9"}
    before = await _count(sessions, Message)
    first = await _ingest(sessions, payload)
    again = await _ingest(sessions, {**payload, "body": "Hello (retry with edits)"})
    assert again.duplicate
    assert not again.created_conversation
    assert again.message.id == first.message.id
    assert again.message.body == "Hello"
    assert await _count(sessions, Message) == before + 1


async def test_a_customer_message_reopens_the_thread(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    first = await _ingest(sessions, {"body": "Hi", "external_thread_ref": "t-5"})
    async with identity_transaction(sessions, seed_auth_subject(OLIVIA)) as db:
        await bind_tenant(db, LUMEN)
        conversation = await db.get(Conversation, first.conversation.id)
        assert conversation is not None
        conversation.status = ConversationStatus.CLOSED
    again = await _ingest(sessions, {"body": "Me again", "external_thread_ref": "t-5"})
    assert again.conversation.id == first.conversation.id
    assert again.conversation.status is ConversationStatus.OPEN


async def test_thread_refs_and_message_ids_are_per_tenant(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    """The same provider ids in another tenant never reach this tenant's conversation."""
    lumen = await _ingest(
        sessions, {"body": "Lumen", "external_message_id": "x-1", "external_thread_ref": "x"}
    )
    harbour_channel = seed_id("harbour-catering-test:channel:Office phone")
    harbour = await _ingest(
        sessions,
        {"body": "Harbour", "external_message_id": "x-1", "external_thread_ref": "x"},
        email=HUGO,
        org=HARBOUR,
        channel_id=harbour_channel,
    )
    assert not harbour.duplicate
    assert harbour.created_conversation
    assert harbour.conversation.id != lumen.conversation.id
    assert harbour.conversation.organization_id == HARBOUR


async def test_sender_matching_never_uses_another_tenants_contact(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    harbour_channel = seed_id("harbour-catering-test:channel:Office phone")
    result = await _ingest(
        sessions,
        {"body": "Hi", "sender_email": "luca.vella@example.test"},  # a Lumen contact
        email=HUGO,
        org=HARBOUR,
        channel_id=harbour_channel,
    )
    assert result.conversation.contact_id is None


async def test_disabled_channels_refuse_ingest(sessions: async_sessionmaker[AsyncSession]) -> None:
    async with identity_transaction(sessions, seed_auth_subject(OLIVIA)) as db:
        await bind_tenant(db, LUMEN)
        channel = await db.get(Channel, EMAIL_CHANNEL)
        assert channel is not None
        channel.disabled_at = NOW
    with pytest.raises(ChannelDisabledError):
        await _ingest(sessions, {"body": "Hi"})
