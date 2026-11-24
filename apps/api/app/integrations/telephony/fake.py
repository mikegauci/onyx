"""An in-memory telephony provider for local and e2e runs. Settings refuse it when deployed.

Its webhook is JSON ``{"call_id", "from", "to"}`` signed with HMAC-SHA256 of the raw body
(hex) in ``X-Onyx-Fake-Signature``. SMS sends are recorded and get a fake id; nothing leaves
the process.
"""

import hashlib
import hmac
import json
import uuid
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime

from app.integrations.telephony import (
    CallEvent,
    TelephonyProviderError,
    TelephonySignatureError,
    WebhookAnswer,
)
from app.modules.crm.identity import IdentityError, normalise_phone

HEADER = "x-onyx-fake-signature"


def sign(secret: str, body: bytes) -> str:
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def _e164(value: object) -> str | None:
    if not isinstance(value, str) or not value.startswith("+"):
        return None
    try:
        return normalise_phone(value)
    except IdentityError:
        return None


@dataclass
class SentSms:
    sender: str
    to: str
    text: str


@dataclass
class FakeTelephonyProvider:
    secret: str
    name: str = "fake"
    sent: list[SentSms] = field(default_factory=list)
    fail_sms: bool = False

    def parse_call(
        self, url: str, headers: Mapping[str, str], body: bytes, *, now: datetime
    ) -> CallEvent | None:
        del url
        given = headers.get(HEADER, "")
        if not given or not hmac.compare_digest(given, sign(self.secret, body)):
            raise TelephonySignatureError("bad or missing signature")
        try:
            payload = json.loads(body)
        except (UnicodeDecodeError, json.JSONDecodeError):
            return None
        if not isinstance(payload, dict):
            return None
        call_id, called = payload.get("call_id"), _e164(payload.get("to"))
        if not isinstance(call_id, str) or not 0 < len(call_id) <= 64 or called is None:
            return None
        return CallEvent(call_id, _e164(payload.get("from")), called, now)

    def answer(self) -> WebhookAnswer:
        return WebhookAnswer("", "text/plain")

    async def send_sms(self, sender: str, to: str, text: str) -> str:
        if self.fail_sms:
            raise TelephonyProviderError("rejected", status=400)
        self.sent.append(SentSms(sender, to, text))
        return f"SMfake{uuid.uuid4().hex}"
