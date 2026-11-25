"""Outbound drafts: create, edit, approve, reject and send replies. The only path to a customer.

Every method runs in the request transaction, bound to the caller's workspace (never a tenant
from input), with an explicit ``organization_id`` filter on top of row-level security. Each
change writes its audit entry in the same transaction; entries carry ids, revision numbers and
statuses, never reply text.

The rules that make sending safe:

- Only an **approved** draft is sent, and only the exact revision that was approved (an edit
  after approval puts it back to pending). The database refuses anything else.
- A draft with a quote can only be approved once that quote version is approved and still
  valid, and is only sent while the same version is still approved and valid.
- A draft stops holding after the workspace's expiry time, when the customer writes again, or
  when its quote changes. It must then be drafted again.
- Sending goes through the inbox channel adapter with the draft's id as idempotency key, and
  writes an outbox event in the same transaction, so a retry never sends twice.
"""

import logging
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import insert, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit.record import record_workspace_audit
from app.core.auth.deps import WorkspaceAccess
from app.core.errors import ConflictError, ErrorDetail, NotFoundError, ValidationFailedError
from app.core.outbox.models import OutboxEvent
from app.core.tenancy.models import User
from app.modules.inbox import public as inbox
from app.modules.inbox.models import ConversationStatus, Handler
from app.modules.outbound import schemas
from app.modules.outbound.lifecycle import (
    DEFAULT_ESCALATE_AFTER_HOURS,
    DEFAULT_EXPIRY_HOURS,
    DEFAULT_REMIND_AFTER_HOURS,
    EXPIRY_TEXT,
    OPEN,
    QUOTE_BLOCK_TEXT,
    DraftOrigin,
    DraftStatus,
    ExpiryReason,
    QuoteState,
    can_approve,
    can_edit,
    can_reject,
    can_send,
    expiry_reason,
    quote_block,
)
from app.modules.outbound.models import Draft, Revision, Settings
from app.modules.quotations import public as quotations

logger = logging.getLogger("onyx.outbound")

LIST_LIMIT = 100
OPEN_PER_CONVERSATION = "uq_outbound_drafts_open_per_conversation"
SENT_EVENT = "outbound.reply.sent"
CREATED_EVENT = "outbound.draft.created"  # starts the draft's approval workflow
DECIDED_EVENT = "outbound.draft.decided"  # approved, rejected, sent, expired or superseded


class DraftExistsError(ConflictError):
    default_message = (
        "This conversation already has a reply waiting for approval. Edit or reject that one."
    )


class StaleRevisionError(ConflictError):
    default_message = "The draft changed since you opened it. Reload it and check the new text."


class NotApprovedError(ConflictError):
    default_message = "Only an approved reply can be sent. Ask an approver to approve it first."


class DraftClosedError(ConflictError):
    default_message = "This draft is finished and cannot change. Draft a new reply instead."


def _invalid(field: str, message: str) -> ValidationFailedError:
    return ValidationFailedError(
        message, details=[ErrorDetail(loc=["body", field], msg=message, type="invalid")]
    )


def _quote_state(info: quotations.QuoteState | None) -> QuoteState | None:
    if info is None:
        return None
    return QuoteState(
        status=info.status,
        version=info.version,
        version_approved=info.version_approved,
        valid_until=info.valid_until,
    )


class OutboundService:
    def __init__(self, db: AsyncSession, workspace: WorkspaceAccess) -> None:
        self.db = db
        self.workspace = workspace
        self.tenant = workspace.tenant
        self.org = workspace.tenant.organization_id
        self.actor = workspace.user.id

    # --- shared ----------------------------------------------------------------------------

    async def _audit(self, action: str, draft: Draft, details: dict[str, Any]) -> None:
        await record_workspace_audit(
            self.db,
            self.workspace,
            action=f"outbound.draft.{action}",
            target_type="outbound_draft",
            target_id=draft.id,
            details={
                "conversation_id": str(draft.conversation_id),
                "origin": draft.origin.value,
                **details,
            },
        )

    def _now(self) -> datetime:
        return datetime.now(UTC)

    async def _draft(self, draft_id: uuid.UUID, *, lock: bool = False) -> Draft:
        query = select(Draft).where(Draft.organization_id == self.org, Draft.id == draft_id)
        if lock:
            query = query.with_for_update().execution_options(populate_existing=True)
        draft = await self.db.scalar(query)
        if draft is None:
            raise NotFoundError("Draft not found.")
        return draft

    async def _revisions(self, draft: Draft) -> list[Revision]:
        return list(
            (
                await self.db.scalars(
                    select(Revision)
                    .where(Revision.organization_id == self.org, Revision.draft_id == draft.id)
                    .order_by(Revision.revision)
                )
            ).all()
        )

    async def _current(self, draft: Draft) -> Revision:
        revision = await self.db.scalar(
            select(Revision).where(
                Revision.organization_id == self.org,
                Revision.draft_id == draft.id,
                Revision.revision == draft.current_revision,
            )
        )
        if revision is None:  # pragma: no cover - every draft is created with revision 1
            raise NotFoundError("Draft text not found.")
        return revision

    def _add_revision(
        self,
        draft: Draft,
        number: int,
        body: str,
        author: DraftOrigin,
        template: inbox.RenderedTemplate | None = None,
    ) -> None:
        self.db.add(
            Revision(
                organization_id=self.org,
                draft_id=draft.id,
                revision=number,
                body=body,
                author_kind=author,
                author_user_id=self.actor if author is DraftOrigin.STAFF else None,
                template_id=template.template_id if template else None,
                template_name=template.name if template else None,
                template_language=template.language if template else None,
                template_params=list(template.params) if template else None,
            )
        )

    async def _text_or_template(
        self, conversation_id: uuid.UUID, body: schemas.DraftCreate | schemas.RevisionCreate
    ) -> tuple[str, inbox.RenderedTemplate | None]:
        """The reply text, rendered from the template when one is given (checked for sending)."""
        if body.template is None:
            assert body.body is not None  # noqa: S101 - the schema requires one of them
            return body.body, None
        rendered = await inbox.render_template(
            self.db,
            self.workspace,
            conversation_id,
            body.template.template_id,
            body.template.params,
        )
        return rendered.body, rendered

    async def _staleness(self, draft: Draft, *, lock_quote: bool = False) -> ExpiryReason | None:
        quote = (
            await quotations.quote_state(self.db, self.tenant, draft.quote_id, lock=lock_quote)
            if draft.quote_id is not None
            else None
        )
        return expiry_reason(
            status=draft.status,
            now=self._now(),
            expires_at=draft.expires_at,
            context_at=draft.context_at,
            latest_inbound_at=(
                await inbox.latest_inbound(self.db, self.tenant, [draft.conversation_id])
            ).get(draft.conversation_id),
            approved_quote_version=draft.quote_version if draft.status in OPEN else None,
            quote=_quote_state(quote),
            today=quotations.workspace_today(self.workspace),
        )

    async def _refuse_if_stale(self, draft: Draft, *, lock_quote: bool = False) -> None:
        reason = await self._staleness(draft, lock_quote=lock_quote)
        if reason is not None:
            raise ConflictError(EXPIRY_TEXT[reason])

    async def _close(self, draft: Draft, status: DraftStatus, **fields: Any) -> None:
        draft.status = status
        draft.decided_by_user_id = self.actor
        draft.decided_at = self._now()
        for name, value in fields.items():
            setattr(draft, name, value)
        await self.db.flush()
        await self._emit_decision(draft, status.value)

    async def _emit(self, event_type: str, draft: Draft, payload: dict[str, Any], key: str) -> None:
        # Core insert without RETURNING: the app role may insert outbox events, not read them.
        await self.db.execute(
            insert(OutboxEvent).values(
                id=uuid.uuid4(),
                organization_id=self.org,
                event_type=event_type,
                aggregate_type="outbound_draft",
                aggregate_id=draft.id,
                payload={"draft_id": str(draft.id), **payload},
                idempotency_key=key,
            )
        )

    async def _emit_decision(self, draft: Draft, decision: str) -> None:
        """Tells the draft's approval workflow (PR-021); ids and the decision only."""
        await self._emit(
            DECIDED_EVENT,
            draft,
            {"decision": decision, "revision": draft.current_revision},
            f"{DECIDED_EVENT}:{draft.id}:{decision}:{draft.current_revision}",
        )

    # --- settings --------------------------------------------------------------------------

    async def _settings_row(self) -> Settings | None:
        return await self.db.scalar(select(Settings).where(Settings.organization_id == self.org))

    @staticmethod
    def _settings_out(row: Settings | None) -> schemas.OutboundSettingsOut:
        if row is None:
            return schemas.OutboundSettingsOut(
                expiry_hours=DEFAULT_EXPIRY_HOURS,
                remind_after_hours=DEFAULT_REMIND_AFTER_HOURS,
                escalate_after_hours=DEFAULT_ESCALATE_AFTER_HOURS,
            )
        return schemas.OutboundSettingsOut(
            expiry_hours=row.expiry_hours,
            remind_after_hours=row.remind_after_hours,
            escalate_after_hours=row.escalate_after_hours,
        )

    async def settings(self) -> schemas.OutboundSettingsOut:
        return self._settings_out(await self._settings_row())

    async def update_settings(
        self, body: schemas.OutboundSettingsUpdate
    ) -> schemas.OutboundSettingsOut:
        row = await self._settings_row()
        before = self._settings_out(row)
        remind = body.remind_after_hours or before.remind_after_hours
        escalate = body.escalate_after_hours or before.escalate_after_hours
        if escalate <= remind:
            raise _invalid("escalate_after_hours", "Escalate later than the first reminder.")
        if row is None:
            row = Settings(organization_id=self.org, expiry_hours=body.expiry_hours)
            self.db.add(row)
        row.expiry_hours = body.expiry_hours
        row.remind_after_hours = remind
        row.escalate_after_hours = escalate
        row.updated_by_user_id = self.actor
        await self.db.flush()
        after = self._settings_out(row)
        changes = {
            name: {"from": getattr(before, name), "to": getattr(after, name)}
            for name in ("expiry_hours", "remind_after_hours", "escalate_after_hours")
            if getattr(before, name) != getattr(after, name)
        }
        await record_workspace_audit(
            self.db,
            self.workspace,
            action="outbound.settings.updated",
            target_type="organization",
            target_id=self.org,
            details=changes,
        )
        return after

    # --- reading ---------------------------------------------------------------------------

    async def list_drafts(
        self, *, status: DraftStatus | None, conversation_id: uuid.UUID | None
    ) -> list[schemas.DraftOut]:
        query = select(Draft).where(Draft.organization_id == self.org)
        if status is not None:
            query = query.where(Draft.status == status)
        if conversation_id is not None:
            query = query.where(Draft.conversation_id == conversation_id)
        drafts = (
            await self.db.scalars(
                query.order_by(Draft.created_at.desc(), Draft.id.desc()).limit(LIST_LIMIT)
            )
        ).all()
        return await self._outs(drafts)

    async def detail(self, draft_id: uuid.UUID) -> schemas.DraftDetail:
        draft = await self._draft(draft_id)
        return await self._detail(draft)

    async def _detail(self, draft: Draft) -> schemas.DraftDetail:
        revisions = await self._revisions(draft)
        out = (await self._outs([draft]))[0]
        users = await self._users([r.author_user_id for r in revisions])
        return schemas.DraftDetail(
            **out.model_dump(),
            revisions=[
                schemas.RevisionOut(
                    revision=r.revision,
                    body=r.body,
                    template=_template_ref(r),
                    author_kind=r.author_kind,
                    author=users.get(r.author_user_id) if r.author_user_id else None,
                    created_at=r.created_at,
                )
                for r in revisions
            ],
        )

    async def _users(
        self, ids: Sequence[uuid.UUID | None]
    ) -> dict[uuid.UUID, schemas.DraftUserRef]:
        wanted = {i for i in ids if i is not None}
        if not wanted:
            return {}
        rows = await self.db.execute(select(User.id, User.display_name).where(User.id.in_(wanted)))
        found = {row.id: row.display_name for row in rows}
        return {
            i: schemas.DraftUserRef(id=i, label=found.get(i) or "Former member") for i in wanted
        }

    async def _outs(self, drafts: Sequence[Draft]) -> list[schemas.DraftOut]:
        if not drafts:
            return []
        conversation_ids = list({d.conversation_id for d in drafts})
        subjects = await inbox.subjects(self.db, self.tenant, conversation_ids)
        latest = await inbox.latest_inbound(self.db, self.tenant, conversation_ids)
        current = {
            (r.draft_id, r.revision): r
            for r in (
                await self.db.scalars(
                    select(Revision).where(
                        Revision.organization_id == self.org,
                        Revision.draft_id.in_([d.id for d in drafts]),
                    )
                )
            ).all()
        }
        users = await self._users(
            [
                user
                for d in drafts
                for user in (
                    d.approved_by_user_id,
                    d.decided_by_user_id,
                    d.sent_by_user_id,
                    d.created_by_user_id,
                )
            ]
        )
        today = quotations.workspace_today(self.workspace)
        now = self._now()
        outs: list[schemas.DraftOut] = []
        for draft in drafts:
            info = (
                await quotations.quote_state(self.db, self.tenant, draft.quote_id)
                if draft.quote_id is not None
                else None
            )
            reason = draft.expiry_reason or expiry_reason(
                status=draft.status,
                now=now,
                expires_at=draft.expires_at,
                context_at=draft.context_at,
                latest_inbound_at=latest.get(draft.conversation_id),
                approved_quote_version=draft.quote_version,
                quote=_quote_state(info),
                today=today,
            )
            status = DraftStatus.EXPIRED if reason is not None else draft.status
            outs.append(
                schemas.DraftOut(
                    id=draft.id,
                    conversation_id=draft.conversation_id,
                    conversation_subject=subjects.get(draft.conversation_id, ""),
                    origin=draft.origin,
                    status=status,
                    current_revision=draft.current_revision,
                    body=rev.body
                    if (rev := current.get((draft.id, draft.current_revision)))
                    else "",
                    template=_template_ref(rev) if rev else None,
                    quote=self._quote_ref(draft, info, today, open_=status in OPEN),
                    expires_at=draft.expires_at,
                    expiry=(
                        schemas.ExpiryOut(code=reason, message=EXPIRY_TEXT[reason])
                        if reason is not None
                        else None
                    ),
                    approved_revision=draft.approved_revision,
                    approved_by=_ref(users, draft.approved_by_user_id),
                    approved_at=draft.approved_at,
                    rejection_reason=draft.rejection_reason,
                    decided_by=_ref(users, draft.decided_by_user_id),
                    decided_at=draft.decided_at,
                    sent_message_id=draft.sent_message_id,
                    sent_by=_ref(users, draft.sent_by_user_id),
                    sent_at=draft.sent_at,
                    created_by=_ref(users, draft.created_by_user_id),
                    created_at=draft.created_at,
                    updated_at=draft.updated_at,
                )
            )
        return outs

    def _quote_ref(
        self,
        draft: Draft,
        info: quotations.QuoteState | None,
        today: Any,
        *,
        open_: bool,
    ) -> schemas.DraftQuoteRef | None:
        if info is None:
            return None
        state = _quote_state(info)
        block = (
            quote_block(state, today)
            if state is not None and open_ and draft.status is DraftStatus.PENDING
            else None
        )
        return schemas.DraftQuoteRef(
            id=info.id,
            number=info.number,
            status=info.status,
            version=info.version,
            approved_version=draft.quote_version,
            blocked=(
                schemas.QuoteBlockOut(code=block, message=QUOTE_BLOCK_TEXT[block])
                if block is not None
                else None
            ),
        )

    # --- creating --------------------------------------------------------------------------

    async def _expiry_hours(self) -> int:
        row = await self._settings_row()
        return row.expiry_hours if row else DEFAULT_EXPIRY_HOURS

    async def _open_draft(self, conversation_id: uuid.UUID) -> Draft | None:
        return await self.db.scalar(
            select(Draft)
            .where(
                Draft.organization_id == self.org,
                Draft.conversation_id == conversation_id,
                Draft.status.in_(list(OPEN)),
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )

    async def _create(
        self,
        conversation_id: uuid.UUID,
        body: str,
        quote_id: uuid.UUID | None,
        origin: DraftOrigin,
        details: dict[str, Any] | None = None,
        *,
        template: inbox.RenderedTemplate | None = None,
    ) -> Draft:
        now = self._now()
        draft = Draft(
            organization_id=self.org,
            conversation_id=conversation_id,
            origin=origin,
            status=DraftStatus.PENDING,
            current_revision=1,
            quote_id=quote_id,
            context_at=(await inbox.latest_inbound(self.db, self.tenant, [conversation_id])).get(
                conversation_id
            ),
            expires_at=now + timedelta(hours=await self._expiry_hours()),
            created_by_user_id=self.actor,
        )
        try:
            async with self.db.begin_nested():
                self.db.add(draft)
                await self.db.flush()
        except IntegrityError as exc:
            if OPEN_PER_CONVERSATION in str(exc.orig):
                raise DraftExistsError from exc
            raise
        self._add_revision(draft, 1, body, origin, template)
        await self.db.flush()
        row = await self._settings_row()
        created = self._settings_out(row)
        await self._emit(
            CREATED_EVENT,
            draft,
            {
                "remind_at": (now + timedelta(hours=created.remind_after_hours)).isoformat(),
                "escalate_at": (now + timedelta(hours=created.escalate_after_hours)).isoformat(),
                "expires_at": draft.expires_at.isoformat(),
            },
            f"{CREATED_EVENT}:{draft.id}",
        )
        await self._audit(
            "created",
            draft,
            {"revision": 1, "quote_id": str(quote_id) if quote_id else None, **(details or {})},
        )
        return draft

    async def _conversation(self, conversation_id: uuid.UUID) -> inbox.Thread:
        thread = await inbox.get_thread(self.db, self.tenant, conversation_id, limit=1)
        if thread is None:
            raise NotFoundError("Conversation not found.")
        if thread.status is ConversationStatus.CLOSED:
            raise ConflictError("Reopen the conversation before drafting a reply.")
        return thread

    async def _check_quote(self, thread: inbox.Thread, quote_id: uuid.UUID) -> None:
        info = await quotations.quote_state(self.db, self.tenant, quote_id)
        if info is None:
            raise _invalid("quote_id", "Quote not found.")
        if thread.contact_id is None or info.contact_id != thread.contact_id:
            raise _invalid(
                "quote_id", "The quote is for a different contact than this conversation."
            )

    async def create_staff_draft(
        self, conversation_id: uuid.UUID, body: schemas.DraftCreate
    ) -> schemas.DraftDetail:
        thread = await self._conversation(conversation_id)
        if body.quote_id is not None:
            await self._check_quote(thread, body.quote_id)
        existing = await self._open_draft(thread.conversation_id)
        if existing is not None:
            reason = await self._staleness(existing)
            if reason is None:
                raise DraftExistsError
            await self._close(existing, DraftStatus.EXPIRED, expiry_reason=reason)
            await self._audit("expired", existing, {"reason": reason.value})
        text, template = await self._text_or_template(thread.conversation_id, body)
        draft = await self._create(
            thread.conversation_id,
            text,
            body.quote_id,
            DraftOrigin.STAFF,
            {"template": template.name} if template else None,
            template=template,
        )
        return await self._detail(draft)

    async def create_assistant_draft(
        self,
        conversation_id: uuid.UUID,
        body: str,
        quote_id: uuid.UUID | None,
        run_id: uuid.UUID,
    ) -> uuid.UUID:
        """The assistant's proposal, waiting for approval. Replaces any open draft."""
        existing = await self._open_draft(conversation_id)
        if existing is not None:
            await self._close(existing, DraftStatus.SUPERSEDED)
            await self._audit("superseded", existing, {"run_id": str(run_id)})
        draft = await self._create(
            conversation_id, body, quote_id, DraftOrigin.ASSISTANT, {"run_id": str(run_id)}
        )
        return draft.id

    # --- changing --------------------------------------------------------------------------

    def _check_base(self, draft: Draft, revision: int) -> None:
        if draft.status not in OPEN:
            raise DraftClosedError
        if revision != draft.current_revision:
            raise StaleRevisionError

    def _reset_approval(self, draft: Draft) -> None:
        draft.status = DraftStatus.PENDING
        draft.approved_revision = None
        draft.approved_by_user_id = None
        draft.approved_at = None
        draft.quote_version = None

    async def revise(
        self, draft_id: uuid.UUID, body: schemas.RevisionCreate
    ) -> schemas.DraftDetail:
        draft = await self._draft(draft_id, lock=True)
        if not can_edit(draft.status):
            raise DraftClosedError
        self._check_base(draft, body.base_revision)
        await self._refuse_if_stale(draft)
        text, template = await self._text_or_template(draft.conversation_id, body)
        current = await self._current(draft)
        same_template = (
            (current.template_id, current.template_params)
            == (template.template_id, list(template.params))
            if template
            else current.template_id is None
        )
        if text == current.body and same_template:
            return await self._detail(draft)
        was_approved = draft.status is DraftStatus.APPROVED
        number = draft.current_revision + 1
        self._add_revision(draft, number, text, DraftOrigin.STAFF, template)
        draft.current_revision = number
        self._reset_approval(draft)
        await self.db.flush()
        await self._audit(
            "revised", draft, {"revision": number, "approval_withdrawn": was_approved}
        )
        return await self._detail(draft)

    async def approve(
        self, draft_id: uuid.UUID, body: schemas.DraftApproveRequest
    ) -> schemas.DraftDetail:
        draft = await self._draft(draft_id, lock=True)
        if not can_approve(draft.status):
            raise DraftClosedError
        self._check_base(draft, body.revision)
        await self._refuse_if_stale(draft)

        current = await self._current(draft)
        if body.body is not None and current.template_id is not None:
            raise _invalid(
                "body", "A template reply cannot be edited as text; change its values instead."
            )
        edited = body.body is not None and body.body != current.body
        if draft.status is DraftStatus.APPROVED and not edited:
            return await self._detail(draft)  # already approved as it is

        quote_version: int | None = None
        if draft.quote_id is not None:
            info = await quotations.quote_state(self.db, self.tenant, draft.quote_id)
            state = _quote_state(info)
            if info is None or state is None:
                raise ConflictError("The quote is no longer available.")
            block = quote_block(state, quotations.workspace_today(self.workspace))
            if block is not None:
                raise ConflictError(QUOTE_BLOCK_TEXT[block])
            quote_version = info.version

        if edited:
            assert body.body is not None  # noqa: S101 - edited implies a body
            number = draft.current_revision + 1
            self._add_revision(draft, number, body.body, DraftOrigin.STAFF)
            draft.current_revision = number
            await self.db.flush()
            await self._audit("revised", draft, {"revision": number, "approval_withdrawn": False})

        draft.status = DraftStatus.APPROVED
        draft.approved_revision = draft.current_revision
        draft.approved_by_user_id = self.actor
        draft.approved_at = self._now()
        draft.quote_version = quote_version
        await self.db.flush()
        await self._emit_decision(draft, "approved")
        await self._audit(
            "approved",
            draft,
            {
                "revision": draft.current_revision,
                "edited": edited,
                "quote_id": str(draft.quote_id) if draft.quote_id else None,
                "quote_version": quote_version,
            },
        )
        return await self._detail(draft)

    async def reject(self, draft_id: uuid.UUID, body: schemas.RejectRequest) -> schemas.DraftDetail:
        draft = await self._draft(draft_id, lock=True)
        if not can_reject(draft.status):
            raise DraftClosedError
        await self._close(draft, DraftStatus.REJECTED, rejection_reason=body.reason)
        await self._audit("rejected", draft, {"revision": draft.current_revision})
        thread = await inbox.get_thread(self.db, self.tenant, draft.conversation_id, limit=1)
        if thread is not None and thread.handler is Handler.ASSISTANT:
            await inbox.hand_to_staff(
                self.db, self.workspace, draft.conversation_id, "A reviewer rejected the draft."
            )
        return await self._detail(draft)

    # --- sending ---------------------------------------------------------------------------

    async def send(self, draft_id: uuid.UUID) -> tuple[schemas.DraftDetail, bool]:
        """Send the approved revision once. Returns the draft and whether it was already sent."""
        draft = await self._draft(draft_id, lock=True)
        if draft.status is DraftStatus.SENT:
            return await self._detail(draft), True
        if not can_send(draft.status):
            if draft.status is DraftStatus.PENDING:
                raise NotApprovedError
            raise DraftClosedError
        # Share-lock the quote so it cannot be revised or decided while the reply goes out.
        await self._refuse_if_stale(draft, lock_quote=True)

        revision = draft.approved_revision
        if revision is None or revision != draft.current_revision:  # pragma: no cover - CHECK
            raise NotApprovedError
        current = await self._current(draft)
        template: inbox.RenderedTemplate | None = None
        if current.template_id is not None:
            # Re-checked at send time: the template may have been paused or changed since.
            template = await inbox.render_template(
                self.db,
                self.workspace,
                draft.conversation_id,
                current.template_id,
                current.template_params or [],
            )
            if template.body != current.body:
                raise ConflictError(
                    "The template's wording changed since this reply was approved. Revise the "
                    "reply and approve it again."
                )
        sent = await inbox.send_reply(
            self.db,
            self.workspace,
            draft.conversation_id,
            current.body,
            idempotency_key=f"outbound-{draft.id}",
            template=template,
        )
        draft.status = DraftStatus.SENT
        draft.sent_message_id = sent.message_id
        draft.sent_by_user_id = self.actor
        draft.sent_at = self._now()
        await self.db.flush()
        await self._emit_decision(draft, "sent")

        payload = {
            "draft_id": str(draft.id),
            "conversation_id": str(draft.conversation_id),
            "message_id": str(sent.message_id),
            "revision": revision,
            "quote_id": str(draft.quote_id) if draft.quote_id else None,
            "quote_version": draft.quote_version,
        }
        # Core insert without RETURNING: the app role may insert outbox events, not read them.
        await self.db.execute(
            insert(OutboxEvent).values(
                id=uuid.uuid4(),
                organization_id=self.org,
                event_type=SENT_EVENT,
                aggregate_type="outbound_draft",
                aggregate_id=draft.id,
                payload=payload,
                idempotency_key=f"{SENT_EVENT}:{draft.id}",
            )
        )
        await self._audit(
            "sent",
            draft,
            {
                "revision": revision,
                "message_id": str(sent.message_id),
                "quote_id": payload["quote_id"],
                "quote_version": draft.quote_version,
            },
        )
        logger.info(
            "outbound reply sent",
            extra={"fields": {"draft_id": str(draft.id), "message_id": str(sent.message_id)}},
        )
        return await self._detail(draft), False


def _ref(users: dict[uuid.UUID, schemas.DraftUserRef], user_id: uuid.UUID | None) -> Any:
    return users.get(user_id) if user_id is not None else None


def _template_ref(revision: Revision) -> schemas.TemplateRef | None:
    if revision.template_id is None:
        return None
    return schemas.TemplateRef(
        template_id=revision.template_id,
        name=revision.template_name or "",
        language=revision.template_language or "",
        params=list(revision.template_params or []),
    )
