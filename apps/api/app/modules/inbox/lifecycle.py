"""Conversation status and handoff rules. The backend alone decides what is allowed.

Status::

    open ⇄ waiting_on_customer
    open | waiting_on_customer → closed
    closed → open (reopen)

A customer message on a waiting or closed conversation reopens it (``STATUS_AFTER_INBOUND``).
Staff cannot log a reply to a closed conversation; they reopen it first. Notes are always
allowed.

Handler (who is expected to respond)::

    assistant → staff   any inbox writer, with a reason (human handoff)
    staff → assistant   inbox managers only

New conversations start with staff. The assistant arrives in PR-015 and only ever drafts for
staff approval (PR-016); the handler field records whose turn it is, it sends nothing.
"""

from app.modules.inbox.models import ConversationStatus, Handler, MessageDirection

OPEN, WAITING, CLOSED = (
    ConversationStatus.OPEN,
    ConversationStatus.WAITING_ON_CUSTOMER,
    ConversationStatus.CLOSED,
)

TRANSITIONS: dict[ConversationStatus, frozenset[ConversationStatus]] = {
    OPEN: frozenset({WAITING, CLOSED}),
    WAITING: frozenset({OPEN, CLOSED}),
    CLOSED: frozenset({OPEN}),
}

INITIAL_HANDLER = Handler.STAFF


def allowed_transitions(current: ConversationStatus) -> list[ConversationStatus]:
    return sorted(TRANSITIONS[current])


def can_transition(current: ConversationStatus, target: ConversationStatus) -> bool:
    return target in TRANSITIONS[current]


# A customer writing again always puts the conversation back in the open queue.
STATUS_AFTER_INBOUND = OPEN


def can_post(current: ConversationStatus, direction: MessageDirection) -> bool:
    """Replies need a conversation that is not closed; notes and customer messages do not."""
    return not (direction is MessageDirection.OUTBOUND and current is CLOSED)


def handoff_needs_manager(target: Handler) -> bool:
    """Handing work to the assistant is a policy decision; taking it back is always allowed."""
    return target is Handler.ASSISTANT
