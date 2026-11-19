"""WhatsApp provider contract (provider-neutral) and the process-wide configured provider.

The inbox WhatsApp channel and the webhook route depend on ``WhatsAppProvider``, never on
Meta directly. ``configure`` is called once at startup (or by tests with a fake); with no
provider configured, WhatsApp channels report ``connected: false`` and refuse to send or
receive, and the webhook answers 503.

Provider data is untrusted: it is validated and normalised before it reaches the inbox, and
message bodies and phone numbers are never logged.
"""

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Protocol


class WhatsAppProviderError(Exception):
    """A provider call failed. ``code`` is a short machine reason; never message content."""

    def __init__(self, code: str, *, retryable: bool, status: int | None = None) -> None:
        self.code = code
        self.retryable = retryable
        self.status = status
        super().__init__(f"whatsapp provider error: {code}")


@dataclass(frozen=True)
class TemplateUse:
    """An approved message template with its body parameters, in order ({{1}}, {{2}}, ...)."""

    name: str
    language: str
    params: tuple[str, ...] = ()


@dataclass(frozen=True)
class OutgoingWhatsApp:
    phone_number_id: str  # the business number it is sent from
    to: str  # the customer's number, E.164 with "+"
    callback_data: str  # echoed back in status webhooks; ids only
    text: str | None = None  # a free-form message (only inside the 24-hour window)
    template: TemplateUse | None = None  # otherwise an approved template


@dataclass(frozen=True)
class TemplateInfo:
    """One message template as the provider reports it."""

    provider_id: str
    name: str
    language: str
    category: str  # lower case: utility, marketing, authentication
    status: str  # lower case: approved, pending, rejected, paused, disabled, ...
    body: str | None
    param_count: int
    supported: bool  # False when it needs header media/variables or named parameters


class WhatsAppProvider(Protocol):
    name: str

    async def send(self, message: OutgoingWhatsApp) -> str:
        """Send one message; returns the provider's message id. Raises ``WhatsAppProviderError``."""
        ...

    async def list_templates(self, waba_id: str) -> Sequence[TemplateInfo]:
        """All templates of a WhatsApp Business account. Raises ``WhatsAppProviderError``."""
        ...


@dataclass(frozen=True)
class WhatsAppConfig:
    provider: WhatsAppProvider
    app_secret: str
    verify_token: str
    stop_words: frozenset[str] = field(
        default_factory=lambda: frozenset({"stop", "unsubscribe", "ieqaf"})
    )


_config: WhatsAppConfig | None = None


def configure(config: WhatsAppConfig | None) -> None:
    global _config  # one provider per process, set at startup
    _config = config


def current() -> WhatsAppConfig | None:
    return _config
