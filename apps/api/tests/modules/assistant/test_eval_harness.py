"""The live evaluation harness works end to end with a scripted model (no provider, no cost)."""

import asyncio

from pydantic_ai import Agent
from pydantic_ai.messages import ModelMessage, ModelResponse, ToolCallPart, ToolReturnPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from app.modules.assistant.prompt import INSTRUCTIONS
from app.modules.assistant.schemas import AssistantOutput
from app.modules.assistant.tools import TOOLS as REAL_TOOLS
from evals.assistant_cases import CASES
from evals.run_assistant import TOOLS, EvalDeps, run_case


def _scripted(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
    returned = any(isinstance(p, ToolReturnPart) for m in messages for p in getattr(m, "parts", []))
    if not returned:
        return ModelResponse(parts=[ToolCallPart("search_products", {"query": "arc brass 30"})])
    output = {
        "action": "draft_quote",
        "confidence": "high",
        "reply_draft": "Hi, the brass Arc pendant is in stock; a quote follows.",
        "lines": [{"sku": "ARC-P-30-BRS", "quantity": 2}],
    }
    return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, output)])


def _agent() -> Agent[EvalDeps, AssistantOutput]:
    return Agent(
        FunctionModel(_scripted),
        output_type=AssistantOutput,
        instructions=INSTRUCTIONS,
        retries={"output": 1},
        tools=TOOLS,
    )


def test_eval_tools_mirror_the_production_tools() -> None:
    assert [t.name for t in TOOLS] == [t.name for t in REAL_TOOLS]
    assert [t.description for t in TOOLS] == [t.description for t in REAL_TOOLS]


def test_a_grounded_draft_passes_and_a_missing_contact_fails() -> None:
    clear = next(c for c in CASES if c.name == "clear_request")
    no_contact = next(c for c in CASES if c.name == "no_contact")
    ok, detail, _, _ = asyncio.run(run_case(_agent(), clear))
    assert ok, detail
    ok, detail, _, _ = asyncio.run(run_case(_agent(), no_contact))
    assert ok, detail  # the scripted draft is escalated by the rules, as the case expects
    assert "no_contact" in detail
