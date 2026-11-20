"""The Stripe adapter: Checkout sessions and billing portal sessions over the REST API.

Form-encoded requests with an ``Idempotency-Key``. Errors carry Stripe's error code only,
never the response body (which can echo customer details).
"""

import httpx

from app.integrations.billing import (
    BillingProviderError,
    CheckoutRequest,
    CheckoutSession,
)

API = "https://api.stripe.com"
RETRYABLE = frozenset({408, 409, 429, 500, 502, 503, 504})


class StripeProvider:
    name = "stripe"

    def __init__(
        self,
        api_key: str,
        *,
        timeout: float = 10.0,
        transport: httpx.AsyncBaseTransport | None = None,
        base_url: str = API,
    ) -> None:
        self._client = httpx.AsyncClient(
            base_url=base_url,
            timeout=timeout,
            transport=transport,
            headers={"Authorization": f"Bearer {api_key}"},
        )

    async def _post(self, path: str, data: dict[str, str], key: str | None = None) -> dict:  # type: ignore[type-arg]
        headers = {"Idempotency-Key": key} if key else {}
        try:
            response = await self._client.post(path, data=data, headers=headers)
        except httpx.TimeoutException as exc:
            raise BillingProviderError("timeout", retryable=True) from exc
        except httpx.HTTPError as exc:
            raise BillingProviderError("network", retryable=True) from exc
        if response.status_code >= 400:
            try:
                code = str(response.json().get("error", {}).get("code") or response.status_code)
            except ValueError:
                code = str(response.status_code)
            raise BillingProviderError(
                code, retryable=response.status_code in RETRYABLE, status=response.status_code
            )
        body = response.json()
        if not isinstance(body, dict):
            raise BillingProviderError("bad_response", retryable=False)
        return body

    async def aclose(self) -> None:
        await self._client.aclose()

    async def create_checkout(self, request: CheckoutRequest) -> CheckoutSession:
        data = {
            "mode": "subscription",
            "line_items[0][price]": request.price_id,
            "line_items[0][quantity]": "1",
            "client_reference_id": request.organization_id,
            "metadata[organization_id]": request.organization_id,
            "subscription_data[metadata][organization_id]": request.organization_id,
            "success_url": request.success_url,
            "cancel_url": request.cancel_url,
        }
        if request.customer_id:
            data["customer"] = request.customer_id
        elif request.customer_email:
            data["customer_email"] = request.customer_email
        body = await self._post("/v1/checkout/sessions", data, request.idempotency_key)
        if not isinstance(body.get("id"), str) or not isinstance(body.get("url"), str):
            raise BillingProviderError("bad_response", retryable=False)
        return CheckoutSession(id=body["id"], url=body["url"])

    async def create_portal(self, customer_id: str, return_url: str) -> str:
        body = await self._post(
            "/v1/billing_portal/sessions", {"customer": customer_id, "return_url": return_url}
        )
        url = body.get("url")
        if not isinstance(url, str):
            raise BillingProviderError("bad_response", retryable=False)
        return url
