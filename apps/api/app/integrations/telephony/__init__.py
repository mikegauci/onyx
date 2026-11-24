"""Telephony provider contract (provider-neutral) for missed-call text-back (VA-004).

A business forwards unanswered calls to a cloud number. The provider calls our webhook for
each forwarded call; Onyx rejects the call (nothing is answered) and records it as missed.
The provider is also the SMS fallback when the caller is not on WhatsApp.

``configure`` is called once at startup (or by tests with a fake). With no provider
configured the telephony webhook answers 503. Provider data is untrusted: the signature is
checked before anything is parsed, and phone numbers are never logged.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


class TelephonySignatureError(Exception):
    """The webhook signature is missing or wrong; nothing in the request is trusted."""


class TelephonyProviderError(Exception):
    """A provider call failed. ``code`` is a short machine reason; never message content."""

    def __init__(self, code: str, *, status: int | None = None) -> None:
        self.code = code
        self.status = status
        super().__init__(f"telephony provider error: {code}")


@dataclass(frozen=True)
class CallEvent:
    """One forwarded (so unanswered) call, as the provider reported it."""

    call_id: str  # the provider's call id; the deduplication key
    caller: str | None  # E.164 with "+", or None when the number was withheld
    called: str  # the cloud number the call was forwarded to, E.164
    occurred_at: datetime


@dataclass(frozen=True)
class WebhookAnswer:
    """What the webhook returns to the provider (e.g. TwiML that rejects the call)."""

    body: str
    media_type: str


class TelephonyProvider(Protocol):
    name: str

    def parse_call(
        self, url: str, headers: Mapping[str, str], body: bytes, *, now: datetime
    ) -> CallEvent | None:
        """Verify the signature, then parse. ``None`` for valid requests that are not a call
        to record. Raises ``TelephonySignatureError`` when the signature is bad or missing."""
        ...

    def answer(self) -> WebhookAnswer:
        """The response that ends the forwarded call without answering it."""
        ...

    async def send_sms(self, sender: str, to: str, text: str) -> str:
        """Send one SMS; returns the provider's message id. Raises ``TelephonyProviderError``."""
        ...


@dataclass(frozen=True)
class TelephonyConfig:
    provider: TelephonyProvider
    webhook_url: str  # the public URL the provider signs (Twilio signs URL + parameters)


_config: TelephonyConfig | None = None


def configure(config: TelephonyConfig | None) -> None:
    global _config  # one provider per process, set at startup
    _config = config


def current() -> TelephonyConfig | None:
    return _config
