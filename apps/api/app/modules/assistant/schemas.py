"""Assistant contracts: the model's structured output and the API's inputs and outputs."""

import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.modules.assistant.models import (
    POLICY_BODY_MAX_LENGTH,
    POLICY_TITLE_MAX_LENGTH,
    TOPIC_PATTERN,
    RunOutcome,
)
from app.modules.assistant.rules import Reason

MAX_LINES = 20
REPLY_MAX_LENGTH = 2000

# --- what the model must return (validated by Pydantic AI; invalid output is retried once) ----


class ProposedLine(BaseModel):
    sku: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=64)]
    quantity: int = Field(ge=1, le=10_000)
    reason: Annotated[str, StringConstraints(strip_whitespace=True, max_length=200)] = Field(
        default="", description="Why this SKU matches what the customer asked for."
    )


class AssistantOutput(BaseModel):
    """The assistant's proposal. The backend checks every part before anything is created."""

    action: Literal["draft_quote", "escalate"] = Field(
        description="draft_quote only when every requested item maps to a SKU found by a tool."
    )
    reply_draft: Annotated[
        str, StringConstraints(strip_whitespace=True, max_length=REPLY_MAX_LENGTH)
    ] = Field(
        default="",
        description="A reply for staff to review. Never state prices, totals, VAT, "
        "discounts or amounts: the quote carries the numbers.",
    )
    lines: list[ProposedLine] = Field(default_factory=list, max_length=MAX_LINES)
    escalation_reason: Annotated[str, StringConstraints(strip_whitespace=True, max_length=300)] = (
        Field(default="", description="Why a person should handle this, when escalating.")
    )
    confidence: Literal["high", "medium", "low"]
    policies_used: list[str] = Field(
        default_factory=list, max_length=5, description="Policy topics quoted in the reply."
    )


# --- API ---------------------------------------------------------------------------------


class _Input(BaseModel):
    model_config = ConfigDict(extra="forbid")


Topic = Annotated[str, StringConstraints(pattern=TOPIC_PATTERN)]


class PolicyUpsert(_Input):
    title: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=1, max_length=POLICY_TITLE_MAX_LENGTH),
    ]
    body: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=1, max_length=POLICY_BODY_MAX_LENGTH),
    ]


class PolicyOut(BaseModel):
    topic: str
    title: str
    body: str
    updated_at: datetime


class QuoteRef(BaseModel):
    id: uuid.UUID
    number: str


class ToolCallOut(BaseModel):
    tool: str
    skus: list[str] = Field(default_factory=list)
    topic: str | None = None
    found: bool | None = None


class ReasonOut(BaseModel):
    """Why a run went to staff: a stable code and the text staff read."""

    code: Reason
    message: str


class RunOut(BaseModel):
    id: uuid.UUID
    conversation_id: uuid.UUID
    outcome: RunOutcome
    reasons: list[ReasonOut]
    quote: QuoteRef | None
    note_message_id: uuid.UUID | None
    tool_calls: list[ToolCallOut]
    model: str | None
    cost_usd_micros: int
    created_at: datetime
