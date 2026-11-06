"""Run the sales assistant's evaluation cases against the configured real model.

    uv run python -m evals.run_assistant --yes

Needs ``ONYX_API_AI_DEFAULT_MODEL`` (or a ``sales_assistant`` workload override), its price and
key. It calls the provider once per case (several requests each), so it costs money: it refuses
to start without ``--yes`` and prints the estimated spend at the end. No database is used: the
tools read the fixture catalogue in ``assistant_cases``, and the same deterministic rules decide
each outcome as in production.
"""

import argparse
import asyncio
import sys
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from pydantic_ai import Agent, RunContext, Tool, UsageLimits

from app.ai.providers import build_model, price_for, resolve_model
from app.core.config import Settings
from app.modules.assistant import tools as real_tools
from app.modules.assistant.prompt import INSTRUCTIONS, build_prompt
from app.modules.assistant.rules import Proposal, SkuFacts, Trace, check, merge_lines
from app.modules.assistant.schemas import AssistantOutput
from app.modules.assistant.service import MAX_REQUESTS, WORKLOAD
from app.modules.inbox.models import ConversationStatus, Handler, MessageDirection
from app.modules.inbox.public import Thread, ThreadMessage
from evals.assistant_cases import CASES, CATALOGUE, POLICIES, Case


@dataclass
class EvalDeps:
    trace: Trace


def _hit(sku: str) -> real_tools.ProductHit:
    description, price, stock, _ = CATALOGUE[sku]
    return real_tools.ProductHit(
        sku=sku,
        description=description,
        unit_price_eur=price,
        prices_include_vat=True,
        vat_percent="18.00",
        stock_available=stock,
        stock_observed_at=datetime(2026, 11, 1, tzinfo=UTC) if stock is not None else None,
    )


async def search_products(ctx: RunContext[EvalDeps], query: str) -> list[real_tools.ProductHit]:
    words = [w for w in query.lower().split() if w]
    found = [
        sku
        for sku, (description, _, _, archived) in CATALOGUE.items()
        if not archived and all(w in f"{sku} {description}".lower() for w in words)
    ][:10]
    ctx.deps.trace.seen_skus.update(found)
    return [_hit(s) for s in found]


async def check_stock(ctx: RunContext[EvalDeps], skus: list[str]) -> list[real_tools.StockFact]:
    out = []
    for raw in skus[:10]:
        sku = raw.strip().upper()
        if sku in CATALOGUE and not CATALOGUE[sku][3]:
            ctx.deps.trace.seen_skus.add(sku)
            hit = _hit(sku)
            out.append(
                real_tools.StockFact(
                    sku=sku,
                    found=True,
                    stock_available=hit.stock_available,
                    stock_observed_at=hit.stock_observed_at,
                )
            )
        else:
            out.append(
                real_tools.StockFact(
                    sku=raw, found=False, stock_available=None, stock_observed_at=None
                )
            )
    return out


async def get_policy(ctx: RunContext[EvalDeps], topic: str) -> real_tools.PolicyText:
    key = topic.strip().lower().replace(" ", "_")
    if key not in POLICIES:
        return real_tools.PolicyText(topic=key, found=False)
    ctx.deps.trace.found_topics.add(key)
    title, body = POLICIES[key]
    return real_tools.PolicyText(topic=key, found=True, title=title, text=body)


# Same names and descriptions as the production tools, so the model sees the same interface.
for fake, real in [
    (search_products, real_tools.search_products),
    (check_stock, real_tools.check_stock),
    (get_policy, real_tools.get_policy),
]:
    fake.__doc__ = real.__doc__

TOOLS = [
    Tool(f, takes_ctx=True, sequential=True) for f in (search_products, check_stock, get_policy)
]


def _facts() -> dict[str, SkuFacts]:
    return {
        sku: SkuFacts(
            archived=archived, has_price=price is not None, has_vat=True, stock_available=stock
        )
        for sku, (_, price, stock, archived) in CATALOGUE.items()
    }


async def run_case(
    agent: Agent[EvalDeps, AssistantOutput], case: Case
) -> tuple[bool, str, int, int]:
    thread = Thread(
        conversation_id=uuid.uuid4(),
        subject="Customer enquiry",
        status=ConversationStatus.OPEN,
        handler=Handler.STAFF,
        contact_id=uuid.uuid4() if case.has_contact else None,
        lead_id=None,
        messages=[
            ThreadMessage(MessageDirection.INBOUND, m, datetime.now(UTC)) for m in case.messages
        ],
    )
    deps = EvalDeps(trace=Trace())
    result = await agent.run(
        build_prompt(thread), deps=deps, usage_limits=UsageLimits(request_limit=MAX_REQUESTS)
    )
    out = result.output
    proposal = Proposal(
        escalate=out.action == "escalate",
        low_confidence=out.confidence == "low",
        reply=out.reply_draft,
        lines=merge_lines((line.sku.strip().upper(), line.quantity) for line in out.lines),
        policies_used=[t.strip().lower() for t in out.policies_used],
    )
    reasons = check(proposal, deps.trace, _facts(), has_contact=case.has_contact)
    outcome = "escalated" if reasons else "drafted"
    skus = {sku for sku, _ in proposal.lines}
    passed = outcome == case.expect and (case.expect == "escalated" or skus == case.skus)
    detail = f"{outcome} reasons={[r.value for r in reasons]} skus={sorted(skus)}"
    usage = result.usage
    return passed, detail, usage.input_tokens, usage.output_tokens


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--yes", action="store_true", help="confirm real provider calls (costs money)"
    )
    parser.add_argument("--case", help="run only this case")
    args = parser.parse_args()
    if not args.yes:
        print("Refusing to call a real provider without --yes (this costs money).")
        return 2
    settings = Settings()
    ref = resolve_model(settings, WORKLOAD)
    if ref.provider == "fake":
        print("No real model configured (ONYX_API_AI_DEFAULT_MODEL).")
        return 2
    price = price_for(settings, ref)
    agent: Agent[EvalDeps, AssistantOutput] = Agent(
        build_model(ref, settings),
        output_type=AssistantOutput,
        instructions=INSTRUCTIONS,
        retries={"output": 1},
        tools=TOOLS,
    )
    cases = [c for c in CASES if args.case in (None, c.name)]
    passed = total_in = total_out = 0
    for case in cases:
        ok, detail, used_in, used_out = await run_case(agent, case)
        passed += ok
        total_in += used_in
        total_out += used_out
        print(f"{'PASS' if ok else 'FAIL'}  {case.name:<20} expected {case.expect:<9} got {detail}")
    cost = price.cost_micros(total_in, total_out) / 1_000_000
    print(
        f"\n{passed}/{len(cases)} passed on {ref.ref}; {total_in} in / {total_out} out tokens, "
        f"about ${cost:.4f}"
    )
    return 0 if passed == len(cases) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
