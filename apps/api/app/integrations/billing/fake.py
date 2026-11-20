"""An in-memory billing provider for local and e2e runs. Settings refuse it when deployed."""

import uuid

from app.integrations.billing import CheckoutRequest, CheckoutSession


class FakeBillingProvider:
    name = "fake"

    def __init__(self) -> None:
        self.checkouts: list[CheckoutRequest] = []
        self.portals: list[tuple[str, str]] = []

    async def create_checkout(self, request: CheckoutRequest) -> CheckoutSession:
        self.checkouts.append(request)
        session = f"cs_test_{uuid.uuid4().hex}"
        return CheckoutSession(id=session, url=f"{request.success_url}&fake_session={session}")

    async def create_portal(self, customer_id: str, return_url: str) -> str:
        self.portals.append((customer_id, return_url))
        return f"{return_url}?fake_portal={customer_id}"
