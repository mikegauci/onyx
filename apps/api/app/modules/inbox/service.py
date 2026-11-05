"""Inbox domain service: the only code that changes inbox rows on behalf of staff.

Every method runs inside the request transaction, bound to the caller's workspace. The tenant
comes from ``WorkspaceAccess`` (never from input); queries add an explicit ``organization_id``
filter on top of row-level security. Each change writes its conversation event and its audit
entry in the same transaction. Audit and event details never contain message text.

Nothing here sends anything to a customer. A reply is passed to the channel adapter, and the
only adapter (manual) records it as ``logged``. Real delivery arrives with PR-016/PR-017.
"""

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Select, exists, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.core.audit.record import record_workspace_audit
from app.core.auth.deps import WorkspaceAccess
from app.core.auth.permissions import Permission, has_permission
from app.core.errors import (
    ConflictError,
    ErrorDetail,
    NotFoundError,
    PermissionDeniedError,
    ValidationFailedError,
)
from app.core.tenancy.models import Membership, User
from app.modules.crm import public as crm
from app.modules.crm.pagination import encode_cursor, paginate
from app.modules.inbox import schemas
from app.modules.inbox.channels.base import (
    ADAPTERS,
    InvalidInboundError,
    OutboundMessage,
    adapter_for,
    parse_occurred_at,
)
from app.modules.inbox.ingest import (
    DUPLICATE_MESSAGE,
    InboxIngest,
    constraint_name,
    record_event,
    set_status,
)
from app.modules.inbox.lifecycle import (
    allowed_transitions,
    can_post,
    can_transition,
    handoff_needs_manager,
)
from app.modules.inbox.models import (
    AuthorKind,
    Channel,
    Conversation,
    DeliveryStatus,
    Event,
    EventKind,
    Handler,
    Message,
    MessageDirection,
    Participant,
)

UNIQUE_CHANNEL_NAME = "uq_inbox_channels_organization_id_name"


class DuplicateChannelError(ConflictError):
    default_message = "A channel with this name already exists in this workspace."


class TransitionNotAllowedError(ConflictError):
    default_message = "This status change is not allowed."


def _invalid(field: str, message: str, kind: str = "invalid") -> ValidationFailedError:
    return ValidationFailedError(
        message, details=[ErrorDetail(loc=["body", field], msg=message, type=kind)]
    )


def _like(term: str) -> str:
    escaped = term.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _page[T](rows: list[T], limit: int, key: Any) -> tuple[list[T], str | None]:
    page = rows[:limit]
    if len(rows) <= limit:
        return page, None
    when, item_id = key(page[-1])
    return page, encode_cursor(when, item_id)


def _user(user_id: uuid.UUID | None, name: str | None) -> schemas.UserRef | None:
    return None if user_id is None else schemas.UserRef(user_id=user_id, display_name=name)


def channel_out(channel: Channel) -> schemas.ChannelOut:
    return schemas.ChannelOut(
        id=channel.id,
        kind=channel.kind,
        name=channel.name,
        connected=channel.kind in ADAPTERS,
        disabled_at=channel.disabled_at,
        created_at=channel.created_at,
    )


def _channel_ref(channel: Channel) -> schemas.ChannelRef:
    return schemas.ChannelRef(id=channel.id, kind=channel.kind, name=channel.name)


def _participant_out(
    participant: Participant, contacts: dict[uuid.UUID, crm.ContactSummary]
) -> schemas.ParticipantOut:
    contact = contacts.get(participant.contact_id) if participant.contact_id else None
    return schemas.ParticipantOut(
        id=participant.id,
        contact=schemas.ContactRef(id=contact.id, full_name=contact.full_name) if contact else None,
        display_name=participant.display_name,
        address=participant.address,
    )


class InboxService:
    def __init__(self, db: AsyncSession, workspace: WorkspaceAccess) -> None:
        self.db = db
        self.workspace = workspace
        self.tenant = workspace.tenant
        self.org = workspace.tenant.organization_id
        self.actor = workspace.user.id

    # --- shared ----------------------------------------------------------------------------

    async def _audit(
        self, action: str, target_type: str, target_id: uuid.UUID, details: dict[str, Any]
    ) -> None:
        await record_workspace_audit(
            self.db,
            self.workspace,
            action=f"inbox.{action}",
            target_type=target_type,
            target_id=target_id,
            details=details,
        )

    async def _event(
        self, conversation: Conversation, kind: EventKind, details: dict[str, Any]
    ) -> None:
        record_event(self.db, conversation, kind, details, self.actor)
        await self._audit(f"conversation.{kind.value}", "conversation", conversation.id, details)

    def _ingest(self) -> InboxIngest:
        return InboxIngest(self.db, self.tenant, actor_user_id=self.actor)

    def _now(self) -> datetime:
        return datetime.now(UTC)

    # --- channels --------------------------------------------------------------------------

    async def list_channels(self, *, include_disabled: bool) -> Sequence[Channel]:
        query = select(Channel).where(Channel.organization_id == self.org)
        if not include_disabled:
            query = query.where(Channel.disabled_at.is_(None))
        return (await self.db.scalars(query.order_by(Channel.name))).all()

    async def get_channel(self, channel_id: uuid.UUID) -> Channel:
        channel = await self.db.scalar(
            select(Channel).where(Channel.organization_id == self.org, Channel.id == channel_id)
        )
        if channel is None:
            raise NotFoundError("Channel not found.")
        return channel

    async def _flush_channel(self) -> None:
        try:
            async with self.db.begin_nested():
                await self.db.flush()
        except IntegrityError as exc:
            if constraint_name(exc) != UNIQUE_CHANNEL_NAME:
                raise
            raise DuplicateChannelError(
                details=[ErrorDetail(loc=["body", "name"], msg="Already used.", type="duplicate")]
            ) from exc

    async def create_channel(self, body: schemas.ChannelCreate) -> Channel:
        channel = Channel(
            organization_id=self.org,
            kind=body.kind,
            name=body.name,
            created_by_user_id=self.actor,
        )
        self.db.add(channel)
        await self._flush_channel()
        await self._audit("channel.created", "channel", channel.id, {"kind": body.kind.value})
        return channel

    async def update_channel(self, channel_id: uuid.UUID, body: schemas.ChannelUpdate) -> Channel:
        channel = await self.get_channel(channel_id)
        changed: list[str] = []
        if body.name is not None and body.name != channel.name:
            channel.name = body.name
            changed.append("name")
        if body.disabled is not None and body.disabled != (channel.disabled_at is not None):
            channel.disabled_at = self._now() if body.disabled else None
            changed.append("disabled")
        if changed:
            await self._flush_channel()
            await self._audit("channel.updated", "channel", channel.id, {"fields": changed})
        return channel

    # --- assignees -------------------------------------------------------------------------

    async def list_assignees(self) -> list[schemas.Assignee]:
        rows = await self.db.execute(
            select(User.id, User.display_name)
            .join(Membership, Membership.user_id == User.id)
            .where(Membership.organization_id == self.org)
            .order_by(User.display_name)
        )
        return [schemas.Assignee(user_id=uid, display_name=name) for uid, name in rows.all()]

    async def _ensure_member(self, user_id: uuid.UUID) -> None:
        is_member = await self.db.scalar(
            select(Membership.id).where(
                Membership.organization_id == self.org, Membership.user_id == user_id
            )
        )
        if is_member is None:
            raise _invalid("assignee_user_id", "Not a member of this workspace.")

    # --- conversations: reading ------------------------------------------------------------

    def _conversation_query(self) -> Select[Conversation, Channel, str]:
        assignee = aliased(User)
        return (
            select(Conversation, Channel, assignee.display_name)
            .join(
                Channel,
                (Channel.id == Conversation.channel_id)
                & (Channel.organization_id == Conversation.organization_id),
            )
            .outerjoin(assignee, assignee.id == Conversation.assignee_user_id)
            .where(Conversation.organization_id == self.org)
        )

    async def _first_participants(
        self, conversation_ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, Participant]:
        if not conversation_ids:
            return {}
        rows = await self.db.scalars(
            select(Participant)
            .where(
                Participant.organization_id == self.org,
                Participant.conversation_id.in_(conversation_ids),
            )
            .order_by(Participant.conversation_id, Participant.created_at.desc())
        )
        # Ordered newest first per conversation, so the last write wins: the earliest.
        return {p.conversation_id: p for p in rows}

    def _summary(
        self,
        conversation: Conversation,
        channel: Channel,
        assignee_name: str | None,
        contacts: dict[uuid.UUID, crm.ContactSummary],
        first: Participant | None,
    ) -> schemas.ConversationSummary:
        contact = contacts.get(conversation.contact_id) if conversation.contact_id else None
        label = (
            (contact.full_name if contact else None)
            or (first.display_name if first else None)
            or (first.address if first else None)
            or "Unknown customer"
        )
        return schemas.ConversationSummary(
            id=conversation.id,
            subject=conversation.subject,
            status=conversation.status,
            handler=conversation.handler,
            channel=_channel_ref(channel),
            assignee=_user(conversation.assignee_user_id, assignee_name),
            contact=schemas.ContactRef(id=contact.id, full_name=contact.full_name)
            if contact
            else None,
            customer_label=label,
            last_message_at=conversation.last_message_at,
            created_at=conversation.created_at,
        )

    async def list_conversations(
        self,
        *,
        queue: schemas.ConversationQueue,
        status: Any,
        channel_id: uuid.UUID | None,
        contact_id: uuid.UUID | None,
        q: str | None,
        limit: int,
        cursor: str | None,
    ) -> tuple[list[schemas.ConversationSummary], str | None]:
        query = self._conversation_query()
        if queue is schemas.ConversationQueue.MINE:
            query = query.where(Conversation.assignee_user_id == self.actor)
        elif queue is schemas.ConversationQueue.UNASSIGNED:
            query = query.where(Conversation.assignee_user_id.is_(None))
        if status is not None:
            query = query.where(Conversation.status == status)
        if channel_id is not None:
            query = query.where(Conversation.channel_id == channel_id)
        if contact_id is not None:
            query = query.where(Conversation.contact_id == contact_id)
        if q:
            pattern = _like(q)
            matching_participant = exists().where(
                Participant.organization_id == Conversation.organization_id,
                Participant.conversation_id == Conversation.id,
                or_(
                    Participant.display_name.ilike(pattern, escape="\\"),
                    Participant.address.ilike(pattern, escape="\\"),
                ),
            )
            query = query.where(
                or_(Conversation.subject.ilike(pattern, escape="\\"), matching_participant)
            )
        query = paginate(
            query, Conversation.last_message_at, Conversation.id, limit=limit, cursor=cursor
        )
        rows = list((await self.db.execute(query)).all())
        page, next_cursor = _page(rows, limit, lambda r: (r[0].last_message_at, r[0].id))
        conversations = [row[0] for row in page]
        contacts = await crm.get_contacts(
            self.db, self.tenant, [c.contact_id for c in conversations if c.contact_id]
        )
        first = await self._first_participants([c.id for c in conversations])
        items = [
            self._summary(conv, channel, name, contacts, first.get(conv.id))
            for conv, channel, name in page
        ]
        return items, next_cursor

    async def get_conversation(
        self, conversation_id: uuid.UUID, *, lock: bool = False
    ) -> Conversation:
        query = select(Conversation).where(
            Conversation.organization_id == self.org, Conversation.id == conversation_id
        )
        if lock:
            # Wait for competing changes, then keep the row locked until the request commits.
            query = query.with_for_update().execution_options(populate_existing=True)
        conversation = await self.db.scalar(query)
        if conversation is None:
            raise NotFoundError("Conversation not found.")
        return conversation

    async def conversation_detail(self, conversation_id: uuid.UUID) -> schemas.ConversationDetail:
        row = (
            await self.db.execute(
                self._conversation_query().where(Conversation.id == conversation_id)
            )
        ).first()
        if row is None:
            raise NotFoundError("Conversation not found.")
        conversation, channel, assignee_name = row
        participants = (
            await self.db.scalars(
                select(Participant)
                .where(
                    Participant.organization_id == self.org,
                    Participant.conversation_id == conversation.id,
                )
                .order_by(Participant.created_at)
            )
        ).all()
        contact_ids = {p.contact_id for p in participants if p.contact_id}
        if conversation.contact_id:
            contact_ids.add(conversation.contact_id)
        contacts = await crm.get_contacts(self.db, self.tenant, contact_ids)
        lead = (
            await crm.get_lead(self.db, self.tenant, conversation.lead_id)
            if conversation.lead_id
            else None
        )
        summary = self._summary(
            conversation,
            channel,
            assignee_name,
            contacts,
            participants[0] if participants else None,
        )
        return schemas.ConversationDetail(
            **summary.model_dump(),
            handoff_reason=conversation.handoff_reason,
            lead=schemas.LeadRef(id=lead.id, title=lead.title) if lead else None,
            participants=[_participant_out(p, contacts) for p in participants],
            status_changed_at=conversation.status_changed_at,
            updated_at=conversation.updated_at,
            allowed_statuses=allowed_transitions(conversation.status),
        )

    # --- conversations: links --------------------------------------------------------------

    async def _active_contact(self, contact_id: uuid.UUID) -> crm.ContactSummary:
        contact = (await crm.get_contacts(self.db, self.tenant, [contact_id])).get(contact_id)
        if contact is None:
            raise _invalid("contact_id", "Contact not found.", "not_found")
        if contact.archived:
            raise _invalid("contact_id", "The contact is archived.")
        return contact

    async def _lead_for(self, lead_id: uuid.UUID, contact_id: uuid.UUID | None) -> crm.LeadSummary:
        lead = await crm.get_lead(self.db, self.tenant, lead_id)
        if lead is None:
            raise _invalid("lead_id", "Lead not found.", "not_found")
        if lead.archived:
            raise _invalid("lead_id", "The lead is archived.")
        if contact_id is not None and lead.contact_id != contact_id:
            raise _invalid("lead_id", "The lead belongs to a different contact.")
        return lead

    # --- conversations: writing ------------------------------------------------------------

    async def create_conversation(self, body: schemas.ConversationCreate) -> tuple[uuid.UUID, bool]:
        """Returns the conversation id and whether the idempotency key was already used."""
        channel = await self.get_channel(body.channel_id)
        adapter = adapter_for(channel.kind)
        contact = await self._active_contact(body.contact_id) if body.contact_id else None
        sender = body.sender or schemas.Sender()
        if contact is None and sender.email is None and sender.phone is None:
            raise _invalid(
                "sender", "Choose a contact, or enter the customer's email or phone.", "missing"
            )
        lead = None
        if body.lead_id is not None:
            lead = await self._lead_for(body.lead_id, contact.id if contact else None)
        try:
            inbound = adapter.parse_inbound(
                {
                    "body": body.body,
                    "occurred_at": body.occurred_at,
                    "sender_name": sender.name,
                    "sender_email": sender.email,
                    "sender_phone": sender.phone,
                    "subject": body.subject,
                    "external_message_id": body.idempotency_key,
                },
                now=self._now(),
            )
        except InvalidInboundError as exc:
            raise _invalid(exc.field, str(exc)) from exc
        result = await self._ingest().ingest(
            channel,
            inbound,
            subject=body.subject,
            contact=contact,
            lead_id=lead.id if lead else None,
        )
        if result.created_conversation:
            await self._audit(
                "conversation.created",
                "conversation",
                result.conversation.id,
                {"channel_id": str(channel.id), "message_id": str(result.message.id)},
            )
        return result.conversation.id, result.duplicate

    async def update_conversation(
        self, conversation_id: uuid.UUID, body: schemas.ConversationUpdate
    ) -> None:
        conversation = await self.get_conversation(conversation_id, lock=True)
        values = body.model_dump(exclude_unset=True)
        subject = values.get("subject")
        if subject is not None and subject != conversation.subject:
            conversation.subject = subject
            await self._event(conversation, EventKind.SUBJECT_CHANGED, {})
        contact_id = conversation.contact_id
        if "contact_id" in values and values["contact_id"] != conversation.contact_id:
            contact_id = values["contact_id"]
            if contact_id is not None:
                await self._active_contact(contact_id)
            previous = conversation.contact_id
            conversation.contact_id = contact_id
            await self._event(
                conversation,
                EventKind.CONTACT_LINKED,
                {
                    "from": str(previous) if previous else None,
                    "contact_id": str(contact_id) if contact_id else None,
                },
            )
        if "lead_id" in values and values["lead_id"] != conversation.lead_id:
            lead_id = values["lead_id"]
            if lead_id is not None:
                await self._lead_for(lead_id, contact_id)
            previous = conversation.lead_id
            conversation.lead_id = lead_id
            await self._event(
                conversation,
                EventKind.LEAD_LINKED,
                {
                    "from": str(previous) if previous else None,
                    "lead_id": str(lead_id) if lead_id else None,
                },
            )
        elif "contact_id" in values and conversation.lead_id is not None and contact_id:
            # A new contact must not leave a lead of somebody else linked.
            await self._lead_for(conversation.lead_id, contact_id)
        await self.db.flush()

    async def assign(self, conversation_id: uuid.UUID, assignee_user_id: uuid.UUID | None) -> None:
        conversation = await self.get_conversation(conversation_id, lock=True)
        if assignee_user_id == conversation.assignee_user_id:
            return
        if assignee_user_id is not None:
            await self._ensure_member(assignee_user_id)
        previous = conversation.assignee_user_id
        conversation.assignee_user_id = assignee_user_id
        kind = EventKind.ASSIGNED if assignee_user_id is not None else EventKind.UNASSIGNED
        await self._event(
            conversation,
            kind,
            {
                "from": str(previous) if previous else None,
                "to": str(assignee_user_id) if assignee_user_id else None,
            },
        )
        await self.db.flush()

    def _check_transition(self, conversation: Conversation, target: Any) -> None:
        if not can_transition(conversation.status, target):
            allowed = ", ".join(s.value for s in allowed_transitions(conversation.status))
            raise TransitionNotAllowedError(
                f"Cannot change status from {conversation.status.value} to {target.value}. "
                f"Allowed: {allowed or 'none'}."
            )

    async def _set_status(self, conversation: Conversation, target: Any) -> None:
        self._check_transition(conversation, target)
        previous = conversation.status
        set_status(self.db, conversation, target, self.actor, reason="staff")
        await self._audit(
            "conversation.status_changed",
            "conversation",
            conversation.id,
            {"from": previous.value, "to": target.value},
        )

    async def change_status(self, conversation_id: uuid.UUID, target: Any) -> None:
        conversation = await self.get_conversation(conversation_id, lock=True)
        await self._set_status(conversation, target)
        await self.db.flush()

    async def handoff(self, conversation_id: uuid.UUID, body: schemas.HandoffRequest) -> None:
        if handoff_needs_manager(body.handler) and not has_permission(
            self.workspace.role, Permission.INBOX_MANAGE
        ):
            raise PermissionDeniedError(
                "Only inbox managers can hand a conversation to the assistant."
            )
        if body.handler is Handler.STAFF and body.reason is None:
            raise _invalid("reason", "Say why the conversation needs a person.", "missing")
        conversation = await self.get_conversation(conversation_id, lock=True)
        if conversation.handler is body.handler:
            raise ConflictError(f"The conversation is already handled by {body.handler.value}.")
        previous = conversation.handler
        conversation.handler = body.handler
        conversation.handoff_reason = body.reason if body.handler is Handler.STAFF else None
        kind = (
            EventKind.HANDED_TO_STAFF
            if body.handler is Handler.STAFF
            else EventKind.HANDED_TO_ASSISTANT
        )
        await self._event(conversation, kind, {"from": previous.value, "to": body.handler.value})
        await self.db.flush()

    # --- messages --------------------------------------------------------------------------

    async def _existing_staff_message(self, channel_id: uuid.UUID, key: str) -> Message | None:
        return await self.db.scalar(
            select(Message).where(
                Message.organization_id == self.org,
                Message.channel_id == channel_id,
                Message.external_message_id == key,
            )
        )

    async def post_message(
        self, conversation_id: uuid.UUID, body: schemas.MessageCreate
    ) -> tuple[Message, bool]:
        conversation = await self.get_conversation(conversation_id, lock=True)
        channel = await self.get_channel(conversation.channel_id)
        if body.kind is schemas.MessageKind.CUSTOMER:
            return await self._log_customer_message(conversation, channel, body)

        if body.idempotency_key is not None:
            existing = await self._existing_staff_message(channel.id, body.idempotency_key)
            if existing is not None:
                return existing, True
        now = self._now()
        try:
            occurred_at = parse_occurred_at(body.occurred_at, now=now)
        except InvalidInboundError as exc:
            raise _invalid(exc.field, str(exc)) from exc

        if body.kind is schemas.MessageKind.REPLY:
            direction = MessageDirection.OUTBOUND
            if not can_post(conversation.status, direction):
                raise ConflictError("Reopen the conversation before logging a reply.")
            adapter = adapter_for(channel.kind)
            first = (await self._first_participants([conversation.id])).get(conversation.id)
            delivery = await adapter.send(
                OutboundMessage(body=body.body, recipient_address=first.address if first else None)
            )
            status, external_id = delivery.status, delivery.external_message_id
        else:
            direction = MessageDirection.NOTE
            status, external_id = DeliveryStatus.LOGGED, None

        message = Message(
            organization_id=self.org,
            conversation_id=conversation.id,
            channel_id=channel.id,
            direction=direction,
            author_kind=AuthorKind.STAFF,
            author_user_id=self.actor,
            body=body.body,
            delivery_status=status,
            external_message_id=external_id or body.idempotency_key,
            occurred_at=occurred_at,
        )
        try:
            async with self.db.begin_nested():
                self.db.add(message)
                await self.db.flush()
        except IntegrityError as exc:
            if constraint_name(exc) != DUPLICATE_MESSAGE or body.idempotency_key is None:
                raise
            existing = await self._existing_staff_message(channel.id, body.idempotency_key)
            assert existing is not None  # noqa: S101 - the constraint just said so
            return existing, True
        if direction is MessageDirection.OUTBOUND and occurred_at > conversation.last_message_at:
            conversation.last_message_at = occurred_at
        await self._audit(
            "message.logged",
            "conversation",
            conversation.id,
            {"message_id": str(message.id), "direction": direction.value},
        )
        if body.set_status is not None and body.set_status is not conversation.status:
            await self._set_status(conversation, body.set_status)
        await self.db.flush()
        return message, False

    async def _log_customer_message(
        self, conversation: Conversation, channel: Channel, body: schemas.MessageCreate
    ) -> tuple[Message, bool]:
        adapter = adapter_for(channel.kind)
        try:
            inbound = adapter.parse_inbound(
                {
                    "body": body.body,
                    "occurred_at": body.occurred_at,
                    "external_message_id": body.idempotency_key,
                },
                now=self._now(),
            )
        except InvalidInboundError as exc:
            raise _invalid(exc.field, str(exc)) from exc
        result = await self._ingest().ingest(channel, inbound, conversation=conversation)
        if result.duplicate:
            return result.message, True
        await self._audit(
            "message.logged",
            "conversation",
            conversation.id,
            {"message_id": str(result.message.id), "direction": "inbound"},
        )
        if body.set_status is not None and body.set_status is not conversation.status:
            await self._set_status(conversation, body.set_status)
        await self.db.flush()
        return result.message, False

    async def message_out(self, message: Message) -> schemas.MessageOut:
        return (await self._messages_out([message]))[0]

    async def _messages_out(self, messages: Sequence[Message]) -> list[schemas.MessageOut]:
        participant_ids = {m.participant_id for m in messages if m.participant_id}
        participants = (
            {
                p.id: p
                for p in (
                    await self.db.scalars(
                        select(Participant).where(
                            Participant.organization_id == self.org,
                            Participant.id.in_(participant_ids),
                        )
                    )
                ).all()
            }
            if participant_ids
            else {}
        )
        contacts = await crm.get_contacts(
            self.db, self.tenant, [p.contact_id for p in participants.values() if p.contact_id]
        )
        author_ids = {m.author_user_id for m in messages if m.author_user_id}
        names: dict[uuid.UUID, str] = {}
        if author_ids:
            rows = await self.db.execute(
                select(User.id, User.display_name).where(User.id.in_(author_ids))
            )
            names = dict(rows.all())
        out = []
        for m in messages:
            participant = participants.get(m.participant_id) if m.participant_id else None
            out.append(
                schemas.MessageOut(
                    id=m.id,
                    direction=m.direction,
                    author_kind=m.author_kind,
                    author=_user(m.author_user_id, names.get(m.author_user_id))
                    if m.author_user_id
                    else None,
                    participant=_participant_out(participant, contacts) if participant else None,
                    body=m.body,
                    delivery_status=m.delivery_status,
                    occurred_at=m.occurred_at,
                    recorded_at=m.recorded_at,
                )
            )
        return out

    async def list_messages(
        self, conversation_id: uuid.UUID, *, limit: int, cursor: str | None
    ) -> tuple[list[schemas.MessageOut], str | None]:
        await self.get_conversation(conversation_id)
        query = select(Message).where(
            Message.organization_id == self.org, Message.conversation_id == conversation_id
        )
        query = paginate(query, Message.occurred_at, Message.id, limit=limit, cursor=cursor)
        rows = list((await self.db.scalars(query)).all())
        page, next_cursor = _page(rows, limit, lambda m: (m.occurred_at, m.id))
        return await self._messages_out(page), next_cursor

    async def list_events(
        self, conversation_id: uuid.UUID, *, limit: int, cursor: str | None
    ) -> tuple[list[schemas.EventOut], str | None]:
        await self.get_conversation(conversation_id)
        query = (
            select(Event, User.display_name)
            .outerjoin(User, User.id == Event.actor_user_id)
            .where(Event.organization_id == self.org, Event.conversation_id == conversation_id)
        )
        query = paginate(query, Event.occurred_at, Event.id, limit=limit, cursor=cursor)
        rows = list((await self.db.execute(query)).all())
        page, next_cursor = _page(rows, limit, lambda r: (r[0].occurred_at, r[0].id))
        items = [
            schemas.EventOut(
                id=event.id,
                kind=event.kind,
                details=event.details,
                actor=_user(event.actor_user_id, name),
                occurred_at=event.occurred_at,
            )
            for event, name in page
        ]
        return items, next_cursor
