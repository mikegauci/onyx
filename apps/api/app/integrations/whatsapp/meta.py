"""Meta WhatsApp Cloud API adapter. The only code that calls the Graph API.

- ``POST /{phone_number_id}/messages`` sends a text or template message. The Cloud API has no
  idempotency key, so send-once is enforced by the inbox (see ``inbox_whatsapp_sends``);
  ``biz_opaque_callback_data`` carries our attempt id and comes back in status webhooks.
- ``GET /{waba_id}/message_templates`` lists templates, following the ``after`` cursor.
- Every call has a timeout. 429, 5xx and Meta's throttling codes are retryable; other errors
  are not. Errors carry the HTTP status and Meta's numeric error code, never content.
"""

import re
from collections.abc import Sequence
from typing import Any

import httpx

from app.integrations.whatsapp import OutgoingWhatsApp, TemplateInfo, WhatsAppProviderError

API_BASE = "https://graph.facebook.com"
PROVIDER = "meta"
GRAPH_VERSION = re.compile(r"v\d{1,2}\.\d")
GRAPH_ID = re.compile(r"\d{1,32}")  # phone number and account ids; nothing else reaches a URL
# Meta's throttling codes: application, account, spam and pair rate limits.
RETRYABLE_CODES = frozenset({"4", "80007", "130429", "131048", "131056", "133016"})
POSITIONAL = re.compile(r"\{\{(\d{1,2})\}\}")
NAMED = re.compile(r"\{\{\s*[A-Za-z_][A-Za-z0-9_]*\s*\}\}")
PAGE_LIMIT = 100
MAX_PAGES = 20
CALLBACK_MAX = 512


def _error(response: httpx.Response) -> WhatsAppProviderError:
    code = "http_error"
    try:
        body = response.json()
        error = body.get("error") if isinstance(body, dict) else None
        if isinstance(error, dict) and isinstance(error.get("code"), int):
            code = str(error["code"])
    except ValueError:
        pass
    retryable = response.status_code == 429 or response.status_code >= 500
    return WhatsAppProviderError(
        code, retryable=retryable or code in RETRYABLE_CODES, status=response.status_code
    )


def template_info(item: dict[str, Any]) -> TemplateInfo | None:
    """Map one Graph API template to ``TemplateInfo``; ``None`` when it is malformed."""
    provider_id, name, language = item.get("id"), item.get("name"), item.get("language")
    if not all(isinstance(v, str) and v for v in (provider_id, name, language)):
        return None
    body: str | None = None
    supported = True
    components = item.get("components")
    for component in components if isinstance(components, list) else []:
        if not isinstance(component, dict):
            continue
        kind = str(component.get("type", "")).upper()
        text = component.get("text")
        if kind == "BODY" and isinstance(text, str):
            body = text
        elif kind == "HEADER":
            # A media header, or a text header with a variable, needs parameters we do not send.
            if component.get("format", "TEXT") != "TEXT" or (
                isinstance(text, str) and "{{" in text
            ):
                supported = False
        elif kind == "BUTTONS":
            buttons = component.get("buttons")
            for button in buttons if isinstance(buttons, list) else []:
                url = button.get("url") if isinstance(button, dict) else None
                if isinstance(url, str) and "{{" in url:
                    supported = False  # dynamic URL buttons need a parameter too
    numbers = sorted({int(n) for n in POSITIONAL.findall(body or "")})
    if body is None or NAMED.search(body) or numbers != list(range(1, len(numbers) + 1)):
        supported = False
    return TemplateInfo(
        provider_id=str(provider_id),
        name=str(name),
        language=str(language),
        category=str(item.get("category", "")).lower(),
        status=str(item.get("status", "")).lower(),
        body=body,
        param_count=len(numbers),
        supported=supported,
    )


class MetaProvider:
    name = PROVIDER

    def __init__(
        self,
        access_token: str,
        *,
        graph_version: str,
        timeout: float,
        transport: httpx.AsyncBaseTransport | None = None,
        base_url: str = API_BASE,
    ) -> None:
        if not GRAPH_VERSION.fullmatch(graph_version):
            raise ValueError("graph_version must look like v23.0")
        self._client = httpx.AsyncClient(
            base_url=f"{base_url}/{graph_version}",
            headers={"Authorization": f"Bearer {access_token}", "User-Agent": "onyx-platform"},
            timeout=timeout,
            transport=transport,
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        try:
            response = await self._client.request(method, path, **kwargs)
        except httpx.TimeoutException as exc:
            raise WhatsAppProviderError("timeout", retryable=True) from exc
        except httpx.HTTPError as exc:
            raise WhatsAppProviderError("network_error", retryable=True) from exc
        if response.status_code >= 400:
            raise _error(response)
        try:
            body = response.json()
        except ValueError as exc:
            raise WhatsAppProviderError("invalid_response", retryable=False) from exc
        if not isinstance(body, dict):
            raise WhatsAppProviderError("invalid_response", retryable=False)
        return body

    async def send(self, message: OutgoingWhatsApp) -> str:
        if not GRAPH_ID.fullmatch(message.phone_number_id):
            raise WhatsAppProviderError("invalid_id", retryable=False)
        if (message.text is None) == (message.template is None):
            raise WhatsAppProviderError("invalid_message", retryable=False)
        payload: dict[str, Any] = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": message.to.removeprefix("+"),
            "biz_opaque_callback_data": message.callback_data[:CALLBACK_MAX],
        }
        if message.text is not None:
            payload["type"] = "text"
            payload["text"] = {"body": message.text, "preview_url": True}
        else:
            assert message.template is not None  # noqa: S101 - checked above
            template: dict[str, Any] = {
                "name": message.template.name,
                "language": {"code": message.template.language},
            }
            if message.template.params:
                template["components"] = [
                    {
                        "type": "body",
                        "parameters": [
                            {"type": "text", "text": p} for p in message.template.params
                        ],
                    }
                ]
            payload["type"] = "template"
            payload["template"] = template
        body = await self._request("POST", f"/{message.phone_number_id}/messages", json=payload)
        messages = body.get("messages")
        first = messages[0] if isinstance(messages, list) and messages else None
        provider_id = first.get("id") if isinstance(first, dict) else None
        if not isinstance(provider_id, str) or not provider_id:
            raise WhatsAppProviderError("invalid_response", retryable=False)
        return provider_id

    async def list_templates(self, waba_id: str) -> Sequence[TemplateInfo]:
        if not GRAPH_ID.fullmatch(waba_id):
            raise WhatsAppProviderError("invalid_id", retryable=False)
        found: list[TemplateInfo] = []
        after: str | None = None
        for _ in range(MAX_PAGES):
            params: dict[str, Any] = {
                "fields": "id,name,language,status,category,components",
                "limit": PAGE_LIMIT,
            }
            if after:
                params["after"] = after
            body = await self._request("GET", f"/{waba_id}/message_templates", params=params)
            data = body.get("data")
            for item in data if isinstance(data, list) else []:
                info = template_info(item) if isinstance(item, dict) else None
                if info is not None:
                    found.append(info)
            paging = body.get("paging")
            cursors = paging.get("cursors") if isinstance(paging, dict) else None
            next_after = cursors.get("after") if isinstance(cursors, dict) else None
            if not isinstance(paging, dict) or "next" not in paging or not next_after:
                break
            after = str(next_after)
        return found
