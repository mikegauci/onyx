"""Deterministic checks on the assistant's proposal. The model proposes; these rules decide.

A proposal becomes a draft quote only when every check passes. Any failure is a reason to hand
the conversation to staff. The rules never trust the model's own claims: grounding is checked
against what the tools actually returned in this run, and price, VAT and stock against the
catalogue as it is now.
"""

import enum
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field


class Reason(enum.StrEnum):
    MODEL_ESCALATED = "model_escalated"  # the model said a person should handle it
    LOW_CONFIDENCE = "low_confidence"
    NO_LINES = "no_lines"  # nothing to quote
    UNGROUNDED_SKU = "ungrounded_sku"  # a SKU no tool returned in this run
    UNKNOWN_SKU = "unknown_sku"  # not in this tenant's catalogue
    ARCHIVED_SKU = "archived_sku"
    MISSING_PRICE = "missing_price"  # no price on the default price list
    MISSING_VAT = "missing_vat"  # the product has no VAT rate
    UNKNOWN_STOCK = "unknown_stock"  # no stock observation, so availability cannot be stated
    INSUFFICIENT_STOCK = "insufficient_stock"
    REPLY_MENTIONS_AMOUNT = "reply_mentions_amount"  # prices/totals belong in the quote only
    REPLY_UNGROUNDED_SKU = "reply_ungrounded_sku"
    UNKNOWN_POLICY = "unknown_policy"  # cites a policy it did not look up, or that does not exist
    UNKNOWN_SOURCE = "unknown_source"  # cites a document passage no search returned this run
    NO_CONTACT = "no_contact"  # the conversation has no CRM contact to quote for
    QUOTE_FAILED = "quote_failed"  # the quotation service refused the draft
    AI_UNAVAILABLE = "ai_unavailable"
    BUDGET_EXCEEDED = "budget_exceeded"
    PROVIDER_FAILED = "provider_failed"  # error, timeout or output that never validated


REASON_TEXT: dict[Reason, str] = {
    Reason.MODEL_ESCALATED: "The assistant asked for a person to handle this.",
    Reason.LOW_CONFIDENCE: "The assistant was not confident in its draft.",
    Reason.NO_LINES: "No products to quote were identified.",
    Reason.UNGROUNDED_SKU: "It proposed a SKU it had not looked up.",
    Reason.UNKNOWN_SKU: "It proposed a SKU that is not in the catalogue.",
    Reason.ARCHIVED_SKU: "It proposed an archived SKU.",
    Reason.MISSING_PRICE: "A proposed SKU has no price on the default price list.",
    Reason.MISSING_VAT: "A proposed SKU has no VAT rate.",
    Reason.UNKNOWN_STOCK: "Stock for a proposed SKU is unknown.",
    Reason.INSUFFICIENT_STOCK: "There is not enough stock for a proposed quantity.",
    Reason.REPLY_MENTIONS_AMOUNT: "The draft reply stated a price, amount or discount.",
    Reason.REPLY_UNGROUNDED_SKU: "The draft reply mentioned a SKU it had not looked up.",
    Reason.UNKNOWN_POLICY: "The draft relied on a policy that is not on record.",
    Reason.UNKNOWN_SOURCE: "The draft cited a document passage it had not found.",
    Reason.NO_CONTACT: "The conversation is not linked to a CRM contact.",
    Reason.QUOTE_FAILED: "The draft quote could not be created.",
    Reason.AI_UNAVAILABLE: "AI is not available for this workspace.",
    Reason.BUDGET_EXCEEDED: "The workspace's AI budget is used up.",
    Reason.PROVIDER_FAILED: "The AI provider did not return a usable answer.",
}

# Currency symbols or codes, a number with two decimals (12.50, 12,50), a percentage, or any
# mention of a discount: prices and terms belong in the approved quote, never in the reply.
_AMOUNT = re.compile(
    r"[€$£]|\b(?:eur|euro|euros|usd|gbp)\b|\b\d+[.,]\d{2}\b|\d\s*%|\bdiscount",
    re.IGNORECASE,
)
# Code-like tokens with a dash, a letter and a digit (ARC-P-30-BRS), the shape of a SKU.
_SKU_LIKE = re.compile(r"\b(?=[A-Z0-9-]*[A-Z])(?=[A-Z0-9-]*\d)[A-Z0-9]+(?:-[A-Z0-9]+)+\b")


@dataclass(frozen=True)
class SkuFacts:
    """The catalogue's current facts about one SKU, for the checks."""

    archived: bool
    has_price: bool
    has_vat: bool
    stock_available: int | None


@dataclass
class Trace:
    """What the tools actually returned in this run (filled in by the tools)."""

    seen_skus: set[str] = field(default_factory=set)
    found_topics: set[str] = field(default_factory=set)
    found_sources: set[str] = field(default_factory=set)  # knowledge chunk ids returned
    calls: list[dict[str, object]] = field(default_factory=list)


@dataclass(frozen=True)
class Proposal:
    escalate: bool
    low_confidence: bool
    reply: str
    lines: list[tuple[str, int]]  # (normalised SKU, total quantity), duplicates merged
    policies_used: list[str]
    sources_used: list[str] = field(default_factory=list)


def merge_lines(lines: Iterable[tuple[str, int]]) -> list[tuple[str, int]]:
    merged: dict[str, int] = {}
    for sku, quantity in lines:
        merged[sku] = merged.get(sku, 0) + quantity
    return list(merged.items())


def check(
    proposal: Proposal,
    trace: Trace,
    facts: Mapping[str, SkuFacts],
    *,
    has_contact: bool,
) -> list[Reason]:
    """Every reason the proposal must go to staff instead of becoming a draft quote."""
    reasons: list[Reason] = []

    def add(reason: Reason) -> None:
        if reason not in reasons:
            reasons.append(reason)

    if proposal.escalate:
        add(Reason.MODEL_ESCALATED)
    if proposal.low_confidence:
        add(Reason.LOW_CONFIDENCE)
    if not proposal.lines:
        add(Reason.NO_LINES)
    if not has_contact:
        add(Reason.NO_CONTACT)
    for sku, quantity in proposal.lines:
        if sku not in trace.seen_skus:
            add(Reason.UNGROUNDED_SKU)
        known = facts.get(sku)
        if known is None:
            add(Reason.UNKNOWN_SKU)
            continue
        if known.archived:
            add(Reason.ARCHIVED_SKU)
        if not known.has_price:
            add(Reason.MISSING_PRICE)
        if not known.has_vat:
            add(Reason.MISSING_VAT)
        if known.stock_available is None:
            add(Reason.UNKNOWN_STOCK)
        elif known.stock_available < quantity:
            add(Reason.INSUFFICIENT_STOCK)
    if _AMOUNT.search(proposal.reply):
        add(Reason.REPLY_MENTIONS_AMOUNT)
    if any(token not in trace.seen_skus for token in _SKU_LIKE.findall(proposal.reply.upper())):
        add(Reason.REPLY_UNGROUNDED_SKU)
    if any(topic not in trace.found_topics for topic in proposal.policies_used):
        add(Reason.UNKNOWN_POLICY)
    if any(source not in trace.found_sources for source in proposal.sources_used):
        add(Reason.UNKNOWN_SOURCE)
    return reasons
