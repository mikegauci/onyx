"""An in-memory email provider for local and e2e runs. Settings refuse it when deployed.

It behaves like Resend where the platform depends on it: one email per idempotency key, and
the same id for a repeat. Nothing leaves the process.
"""

import uuid

from app.integrations.email import EmailProviderError, OutgoingEmail, ReceivedEmail


class FakeEmailProvider:
    name = "fake"

    def __init__(self) -> None:
        self.sent: list[OutgoingEmail] = []
        self._by_key: dict[str, str] = {}

    async def send(self, email: OutgoingEmail) -> str:
        if email.idempotency_key not in self._by_key:
            self._by_key[email.idempotency_key] = f"fake-{uuid.uuid4()}"
            self.sent.append(email)
        return self._by_key[email.idempotency_key]

    async def get_received(self, provider_id: str) -> ReceivedEmail:
        del provider_id  # nothing is ever received by the fake
        raise EmailProviderError("not_found", retryable=False, status=404)
