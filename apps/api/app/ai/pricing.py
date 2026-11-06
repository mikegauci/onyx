"""Token cost in integer USD micro-units (1 USD = 1_000_000). Never floats.

Prices come from configuration (``ONYX_API_AI_MODEL_PRICES``), so they can be updated without a
deploy of new code and are never guessed: a model without a price cannot be called.
"""

from dataclasses import dataclass
from decimal import ROUND_CEILING, Decimal

from app.core.config import AIModelPrice

MICROS_PER_USD = 1_000_000
TOKENS_PER_PRICE_UNIT = 1_000_000  # prices are per million tokens

# The local/test fake model: priced so cost arithmetic is exercised, though it spends nothing.
FAKE_PRICE = AIModelPrice(input_usd_per_mtok=Decimal("1.00"), output_usd_per_mtok=Decimal("2.00"))


@dataclass(frozen=True)
class TokenPrice:
    """Micro-USD per million tokens."""

    input_micros_per_mtok: Decimal
    output_micros_per_mtok: Decimal

    @classmethod
    def from_config(cls, price: AIModelPrice) -> "TokenPrice":
        return cls(
            input_micros_per_mtok=price.input_usd_per_mtok * MICROS_PER_USD,
            output_micros_per_mtok=price.output_usd_per_mtok * MICROS_PER_USD,
        )

    def cost_micros(self, input_tokens: int, output_tokens: int) -> int:
        """Cost rounded up to the next micro-USD, so recorded spend never under-counts."""
        if input_tokens < 0 or output_tokens < 0:
            raise ValueError("Token counts cannot be negative.")
        total = (
            Decimal(input_tokens) * self.input_micros_per_mtok
            + Decimal(output_tokens) * self.output_micros_per_mtok
        ) / TOKENS_PER_PRICE_UNIT
        return int(total.to_integral_value(rounding=ROUND_CEILING))


def estimate_input_tokens(*texts: str) -> int:
    """A deliberately high estimate (~3 characters per token, plus schema/framing overhead).

    Used only to reserve budget before a call; recorded spend uses the provider's counts.
    """
    characters = sum(len(t) for t in texts)
    return -(-characters // 3) + 500
