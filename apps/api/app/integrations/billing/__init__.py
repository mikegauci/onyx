"""Billing provider contract (provider-neutral). Stripe is the only provider (PR-026).

The billing module depends on ``BillingProvider``, never on Stripe directly. Webhook payloads
are untrusted until their signature is checked (``signing.verify``); even then, the tenant is
resolved from Onyx's own customer mapping, not from fields in the payload.
"""

from dataclasses import dataclass
from typing import Protocol


class BillingProviderError(Exception):
    """A provider call failed. ``code`` is a short machine reason, never customer data."""

    def __init__(self, code: str, *, retryable: bool, status: int | None = None) -> None:
        self.code = code
        self.retryable = retryable
        self.status = status
        super().__init__(f"billing provider error: {code}")


@dataclass(frozen=True)
class CheckoutRequest:
    organization_id: str  # set by Onyx; echoed back as client_reference_id and metadata
    price_id: str
    customer_id: str | None  # an existing customer, or None for a new one
    customer_email: str | None
    success_url: str
    cancel_url: str
    idempotency_key: str


@dataclass(frozen=True)
class CheckoutSession:
    id: str
    url: str


class BillingProvider(Protocol):
    name: str

    async def create_checkout(self, request: CheckoutRequest) -> CheckoutSession: ...

    async def create_portal(self, customer_id: str, return_url: str) -> str: ...


@dataclass(frozen=True)
class BillingConfig:
    provider: BillingProvider
    webhook_secret: str
    # plan key → the provider's price id
    prices: dict[str, str]
