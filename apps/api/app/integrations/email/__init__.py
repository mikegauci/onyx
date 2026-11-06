"""Email provider contract (provider-neutral) and the process-wide configured provider.

The inbox email channel and the webhook route depend on ``EmailProvider``, never on Resend
directly. ``configure`` is called once at startup (or by tests with a fake); with no provider
configured, email channels report ``connected: false`` and refuse to send or receive.

Provider data is untrusted: it is validated and normalised before it reaches the inbox, and
message bodies, addresses and subjects are never logged.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol


class EmailProviderError(Exception):
    """A provider call failed. ``code`` is a short machine reason; never message content."""

    def __init__(self, code: str, *, retryable: bool, status: int | None = None) -> None:
        self.code = code
        self.retryable = retryable
        self.status = status
        super().__init__(f"email provider error: {code}")


@dataclass(frozen=True)
class OutgoingEmail:
    from_address: str  # "Name <local@domain>"
    to: str
    subject: str
    text: str
    html: str
    reply_to: str
    idempotency_key: str  # same key + same email within the provider's window = sent once
    headers: Mapping[str, str] = field(default_factory=dict)
    tags: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class ReceivedEmail:
    provider_id: str
    message_id: str | None  # RFC 5322 Message-ID, e.g. "<abc@example.com>"
    from_address: str  # bare address
    from_header: str | None  # "Name <address>" when the provider gives it
    to: tuple[str, ...]
    subject: str | None
    text: str | None
    html: str | None
    headers: Mapping[str, str]  # lower-case names
    created_at: datetime | None
    # SPF/DKIM/DMARC verdicts from the provider, e.g. {"dmarc": "pass"}
    authentication: Mapping[str, str] = field(default_factory=dict)

    @property
    def sender_verified(self) -> bool:
        """False when DMARC failed: the From address is likely forged."""
        return self.authentication.get("dmarc") != "fail"


class EmailProvider(Protocol):
    name: str

    async def send(self, email: OutgoingEmail) -> str:
        """Send one email; returns the provider's id. Raises ``EmailProviderError``."""
        ...

    async def get_received(self, provider_id: str) -> ReceivedEmail:
        """Fetch one received email's content. Raises ``EmailProviderError``."""
        ...


@dataclass(frozen=True)
class EmailConfig:
    provider: EmailProvider
    webhook_secret: str
    inbound_domain: str
    from_domain: str


_config: EmailConfig | None = None


def configure(config: EmailConfig | None) -> None:
    global _config  # one provider per process, set at startup
    _config = config


def current() -> EmailConfig | None:
    return _config
