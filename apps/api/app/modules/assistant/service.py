"""Running the sales assistant on a conversation, and managing its policy texts.

One run: read the thread, call the model through the AI gateway with read-only tools, check
the proposal with ``rules.check``, then either create a draft quote and a draft-reply note, or
write a note explaining why it goes to staff. The run is recorded either way. Nothing is sent
to the customer, and every number in a quote is computed by the quotations service.
"""

import logging
import uuid
from collections.abc import Sequence
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.errors import AIBudgetExceededError, AIProviderError, AIUnavailableError
from app.ai.gateway import AIGateway, AIResult
from app.core.audit.record import record_workspace_audit
from app.core.auth.deps import WorkspaceAccess
from app.core.errors import AppError, ConflictError, NotFoundError
from app.modules.assistant import schemas
from app.modules.assistant.models import Policy, Run, RunOutcome
from app.modules.assistant.prompt import INSTRUCTIONS, build_prompt
from app.modules.assistant.rules import (
    REASON_TEXT,
    Proposal,
    Reason,
    SkuFacts,
    Trace,
    check,
    merge_lines,
)
from app.modules.assistant.tools import TOOLS, AssistantDeps
from app.modules.catalogue import public as catalogue
from app.modules.inbox import public as inbox
from app.modules.inbox.models import ConversationStatus, Handler, MessageDirection
from app.modules.quotations import public as quotations

logger = logging.getLogger("onyx.assistant")

WORKLOAD = "sales_assistant"
# Model requests per attempt: a few tool round trips, the answer and one output retry.
MAX_REQUESTS = 8
# The most one request may add to the context from tool results (10 products, a policy).
TOOL_CONTEXT_TOKENS = 3000


def _run_out(run: Run, quote_numbers: dict[uuid.UUID, str]) -> schemas.RunOut:
    quote = (
        schemas.QuoteRef(id=run.quote_id, number=quote_numbers.get(run.quote_id, ""))
        if run.quote_id is not None
        else None
    )
    return schemas.RunOut(
        id=run.id,
        conversation_id=run.conversation_id,
        outcome=run.outcome,
        reasons=[Reason(r) for r in run.reasons],
        quote=quote,
        note_message_id=run.note_message_id,
        tool_calls=[schemas.ToolCallOut.model_validate(c) for c in run.tool_calls],
        model=run.model,
        cost_usd_micros=run.cost_usd_micros,
        created_at=run.created_at,
    )


def _escalation_note(reasons: Sequence[Reason], model_reason: str) -> str:
    lines = ["The assistant handed this conversation to staff. No quote was drafted.", ""]
    lines += [f"- {REASON_TEXT[r]}" for r in reasons]
    if model_reason:
        lines += ["", f"Assistant's note: {model_reason}"]
    return "\n".join(lines)


def _draft_note(reply: str, quote: quotations.DraftQuote, line_count: int) -> str:
    noun = "line" if line_count == 1 else "lines"
    return "\n".join(
        [
            "Draft reply from the assistant (not sent; review before replying):",
            "",
            reply or "(no reply text)",
            "",
            f"Draft quote {quote.number} with {line_count} {noun}. Onyx calculated the prices, "
            "VAT and totals from the catalogue. Check and approve the quote before sending it.",
        ]
    )


class AssistantService:
    def __init__(self, db: AsyncSession, workspace: WorkspaceAccess) -> None:
        self.db = db
        self.workspace = workspace
        self.tenant = workspace.tenant
        self.org = workspace.tenant.organization_id
        self.actor = workspace.user.id

    # --- runs ------------------------------------------------------------------------------

    async def run(self, conversation_id: uuid.UUID, gateway: AIGateway) -> schemas.RunOut:
        thread = await inbox.get_thread(self.db, self.tenant, conversation_id)
        if thread is None:
            raise NotFoundError("Conversation not found.")
        if thread.status is ConversationStatus.CLOSED:
            raise ConflictError("Reopen the conversation before asking the assistant.")
        if not any(m.direction is MessageDirection.INBOUND for m in thread.messages):
            raise ConflictError("There is no customer message to answer yet.")

        deps = AssistantDeps(
            db=self.db,
            tenant=self.tenant,
            price_list=await catalogue.get_price_list(self.db, self.tenant, None),
            trace=Trace(),
        )
        result: AIResult[schemas.AssistantOutput] | None = None
        failure: Reason | None = None
        try:
            result = await gateway.run_structured(
                organization_id=self.org,
                workload=WORKLOAD,
                output_type=schemas.AssistantOutput,
                instructions=INSTRUCTIONS,
                prompt=build_prompt(thread),
                actor_user_id=self.actor,
                tools=TOOLS,
                deps=deps,
                max_requests=MAX_REQUESTS,
                tool_context_tokens=TOOL_CONTEXT_TOKENS,
            )
        except AIBudgetExceededError:
            failure = Reason.BUDGET_EXCEEDED
        except AIUnavailableError:
            failure = Reason.AI_UNAVAILABLE
        except AIProviderError:
            failure = Reason.PROVIDER_FAILED

        run = Run(
            organization_id=self.org,
            conversation_id=thread.conversation_id,
            outcome=RunOutcome.ESCALATED,
            tool_calls=deps.trace.calls,
            created_by_user_id=self.actor,
        )
        if result is not None:
            run.usage_event_id = result.usage.event_id
            run.model = f"{result.usage.provider}:{result.usage.model}"
            run.cost_usd_micros = result.usage.cost_usd_micros

        reasons: list[Reason] = [failure] if failure is not None else []
        quote: quotations.DraftQuote | None = None
        line_count = 0
        model_reason = ""
        if result is not None:
            output = result.output
            model_reason = output.escalation_reason
            proposal = self._proposal(output)
            reasons = check(
                proposal,
                deps.trace,
                await self._facts(deps, [sku for sku, _ in proposal.lines]),
                has_contact=thread.contact_id is not None,
            )
            if not reasons and thread.contact_id is not None:
                quote = await self._draft(thread, thread.contact_id, proposal)
                line_count = len(proposal.lines)
                if quote is None:
                    reasons = [Reason.QUOTE_FAILED]

        if quote is not None and result is not None:
            run.outcome, run.quote_id = RunOutcome.DRAFTED, quote.id
            body = _draft_note(result.output.reply_draft, quote, line_count)
        else:
            body = _escalation_note(reasons, model_reason)
        run.reasons = [r.value for r in reasons]
        run.note_message_id = await inbox.add_assistant_note(
            self.db, self.tenant, thread.conversation_id, body
        )
        self.db.add(run)
        await self.db.flush()

        if run.outcome is RunOutcome.ESCALATED and thread.handler is Handler.ASSISTANT:
            summary = "; ".join(REASON_TEXT[r] for r in reasons)[:500] or "Needs a person."
            await inbox.hand_to_staff(self.db, self.workspace, thread.conversation_id, summary)
        await record_workspace_audit(
            self.db,
            self.workspace,
            action=f"assistant.run.{run.outcome.value}",
            target_type="conversation",
            target_id=thread.conversation_id,
            details={
                "run_id": str(run.id),
                "reasons": run.reasons,
                "quote_id": str(run.quote_id) if run.quote_id else None,
            },
        )
        logger.info(
            "assistant run",
            extra={"fields": {"run_id": str(run.id), "outcome": run.outcome.value}},
        )
        return _run_out(run, {quote.id: quote.number} if quote else {})

    def _proposal(self, output: schemas.AssistantOutput) -> Proposal:
        lines: list[tuple[str, int]] = []
        for line in output.lines:
            sku = catalogue.normalise_sku(line.sku) or line.sku.strip().upper()
            lines.append((sku, line.quantity))
        return Proposal(
            escalate=output.action == "escalate",
            low_confidence=output.confidence == "low",
            reply=output.reply_draft,
            lines=merge_lines(lines),
            policies_used=[t.strip().lower() for t in output.policies_used],
        )

    async def _facts(self, deps: AssistantDeps, skus: list[str]) -> dict[str, SkuFacts]:
        """The catalogue's current facts, read fresh (never from the model's tool output)."""
        if deps.price_list is None:
            return {}
        ids: dict[uuid.UUID, str] = {}
        for sku in skus:
            variant_id = await catalogue.find_variant_id(self.db, self.tenant, sku)
            if variant_id is not None:
                ids[variant_id] = sku
        infos = await catalogue.get_skus(self.db, self.tenant, ids, deps.price_list.id)
        return {
            ids[variant_id]: SkuFacts(
                archived=info.archived,
                has_price=info.price is not None,
                has_vat=info.vat is not None,
                stock_available=info.stock_available,
            )
            for variant_id, info in infos.items()
        }

    async def _draft(
        self, thread: inbox.Thread, contact_id: uuid.UUID, proposal: Proposal
    ) -> quotations.DraftQuote | None:
        """Create the draft quote atomically; any refusal leaves nothing behind."""
        try:
            async with self.db.begin_nested():
                return await quotations.draft_quote(
                    self.db,
                    self.workspace,
                    title=f"Assistant draft: {thread.subject}",
                    contact_id=contact_id,
                    lead_id=thread.lead_id,
                    lines=[quotations.DraftLine(sku=s, quantity=q) for s, q in proposal.lines],
                )
        except AppError:
            logger.warning("assistant draft quote refused", extra={"fields": {}})
            return None

    async def list_runs(self, conversation_id: uuid.UUID) -> list[schemas.RunOut]:
        if await inbox.get_thread(self.db, self.tenant, conversation_id, limit=1) is None:
            raise NotFoundError("Conversation not found.")
        runs = (
            await self.db.scalars(
                select(Run)
                .where(Run.organization_id == self.org, Run.conversation_id == conversation_id)
                .order_by(Run.created_at.desc(), Run.id.desc())
                .limit(50)
            )
        ).all()
        numbers = await quotations.quote_numbers(
            self.db, self.tenant, [r.quote_id for r in runs if r.quote_id is not None]
        )
        return [_run_out(r, numbers) for r in runs]

    # --- policies --------------------------------------------------------------------------

    async def list_policies(self) -> list[schemas.PolicyOut]:
        rows = (
            await self.db.scalars(
                select(Policy).where(Policy.organization_id == self.org).order_by(Policy.topic)
            )
        ).all()
        return [_policy_out(p) for p in rows]

    async def put_policy(self, topic: str, body: schemas.PolicyUpsert) -> schemas.PolicyOut:
        policy = await self.db.scalar(
            select(Policy).where(Policy.organization_id == self.org, Policy.topic == topic)
        )
        details: dict[str, Any] = {"topic": topic}
        if policy is None:
            policy = Policy(organization_id=self.org, topic=topic, title=body.title, body=body.body)
            self.db.add(policy)
            action = "assistant.policy.created"
        else:
            policy.title, policy.body = body.title, body.body
            action = "assistant.policy.updated"
        policy.updated_by_user_id = self.actor
        await self.db.flush()
        await self.db.refresh(policy)
        await record_workspace_audit(
            self.db,
            self.workspace,
            action=action,
            target_type="assistant_policy",
            target_id=policy.id,
            details=details,
        )
        return _policy_out(policy)

    async def delete_policy(self, topic: str) -> None:
        policy = await self.db.scalar(
            select(Policy).where(Policy.organization_id == self.org, Policy.topic == topic)
        )
        if policy is None:
            raise NotFoundError("Policy not found.")
        await self.db.delete(policy)
        await self.db.flush()
        await record_workspace_audit(
            self.db,
            self.workspace,
            action="assistant.policy.deleted",
            target_type="assistant_policy",
            target_id=policy.id,
            details={"topic": topic},
        )


def _policy_out(policy: Policy) -> schemas.PolicyOut:
    return schemas.PolicyOut(
        topic=policy.topic, title=policy.title, body=policy.body, updated_at=policy.updated_at
    )
