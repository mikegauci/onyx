"""Twilio: voice webhooks for forwarded calls, and SMS for the text-back fallback.

Signature (``X-Twilio-Signature``): base64 HMAC-SHA1, keyed by the auth token, over the full
public webhook URL followed by every POST parameter, sorted by name, as ``name`` + ``value``.
See https://www.twilio.com/docs/usage/security#validating-requests. The URL is our configured
public URL, not the one the proxy hands us, because Twilio signs what it called.

The call is answered with TwiML ``<Reject reason="busy"/>``: nothing is picked up, so the
forwarded call costs no talk time.
"""

import base64
import contextlib
import hashlib
import hmac
from collections.abc import Mapping
from datetime import datetime
from urllib.parse import parse_qsl

import httpx

from app.integrations.telephony import (
    CallEvent,
    TelephonyProviderError,
    TelephonySignatureError,
    WebhookAnswer,
)
from app.modules.crm.identity import IdentityError, normalise_phone

API_BASE = "https://api.twilio.com/2010-04-01"
REJECT = '<?xml version="1.0" encoding="UTF-8"?><Response><Reject reason="busy"/></Response>'
CALL_SID = "CA"
MAX_ID = 64


def signature(auth_token: str, url: str, params: Mapping[str, str]) -> str:
    payload = url + "".join(f"{key}{params[key]}" for key in sorted(params))
    digest = hmac.new(auth_token.encode(), payload.encode(), hashlib.sha1).digest()
    return base64.b64encode(digest).decode()


def _e164(value: str | None) -> str | None:
    if not value or not value.startswith("+"):
        return None  # withheld numbers arrive as "anonymous", "+266696687" style or empty
    try:
        return normalise_phone(value)
    except IdentityError:
        return None


class TwilioProvider:
    name = "twilio"

    def __init__(
        self,
        account_sid: str,
        auth_token: str,
        *,
        timeout: float = 10.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._sid = account_sid
        self._token = auth_token
        self._client = httpx.AsyncClient(
            base_url=API_BASE,
            auth=(account_sid, auth_token),
            timeout=timeout,
            transport=transport,
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    def parse_call(
        self, url: str, headers: Mapping[str, str], body: bytes, *, now: datetime
    ) -> CallEvent | None:
        given = headers.get("x-twilio-signature")
        try:
            params = dict(parse_qsl(body.decode(), keep_blank_values=True, strict_parsing=False))
        except UnicodeDecodeError as exc:
            raise TelephonySignatureError("undecodable body") from exc
        if not given or not hmac.compare_digest(given, signature(self._token, url, params)):
            raise TelephonySignatureError("bad or missing signature")
        if params.get("AccountSid") != self._sid:
            raise TelephonySignatureError("another account")
        call_id = params.get("CallSid", "")
        called = _e164(params.get("To"))
        if not call_id.startswith(CALL_SID) or len(call_id) > MAX_ID or called is None:
            return None
        if params.get("Direction", "inbound") != "inbound":
            return None
        return CallEvent(
            call_id=call_id, caller=_e164(params.get("From")), called=called, occurred_at=now
        )

    def answer(self) -> WebhookAnswer:
        return WebhookAnswer(REJECT, "text/xml")

    async def send_sms(self, sender: str, to: str, text: str) -> str:
        try:
            response = await self._client.post(
                f"/Accounts/{self._sid}/Messages.json",
                data={"From": sender, "To": to, "Body": text},
            )
        except httpx.HTTPError as exc:
            raise TelephonyProviderError("network") from exc
        if response.status_code >= 400:
            code = "rejected"
            with contextlib.suppress(ValueError, TypeError, AttributeError):
                code = f"twilio_{int(response.json().get('code'))}"
            raise TelephonyProviderError(code, status=response.status_code)
        sid = response.json().get("sid")
        if not isinstance(sid, str) or not sid:
            raise TelephonyProviderError("no_id", status=response.status_code)
        return sid[:MAX_ID]
