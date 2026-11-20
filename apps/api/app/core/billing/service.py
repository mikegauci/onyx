"""Billing: the workspace's plan, checkout and portal links, webhooks and the AI usage report.

Webhooks are processed as ``onyx_worker``, bound to the tenant found through Onyx's own
customer mapping. Each provider event id is recorded once, in the same transaction as its
effect, so a retried webhook changes nothing and a failed one is retried by the provider.
"""

import json
import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.ai.gateway import period_start_at
from app.ai.models import AIBudget, AIUsageEvent
from app.core.billing.models import BillingCustomer, BillingSubscription
from app.core.billing.plans import ACTIVE_STATUSES, BASE_MODULES, PLANS, Plan
from app.core.db.context import TenantContext, worker_transaction
from app.core.db.rls import WORKER_ROLE
from app.integrations.billing import BillingConfig, CheckoutRequest
from app.integrations.billing.signing import WebhookSignatureError, verify

logger = logging.getLogger("onyx.billing")

SUBSCRIPTION_EVENTS = frozenset(
    {
        "customer.subscription.created",
        "customer.subscription.updated",
        "customer.subscription.deleted",
    }
)
CHECKOUT_COMPLETED = "checkout.session.completed"
MAX_BODY_BYTES = 512 * 1024


class BillingNotConfiguredError(Exception):
    pass


class NoCustomerError(Exception):
    """The workspace has never completed a checkout, so it has no billing portal yet."""


@dataclass(frozen=True)
class BillingState:
    plan: str | None
    status: str | None
    current_period_end: datetime | None
    cancel_at_period_end: bool
    has_customer: bool


async def state(db: AsyncSession, tenant: TenantContext) -> BillingState:
    org = tenant.organization_id
    sub = await db.scalar(
        select(BillingSubscription).where(BillingSubscription.organization_id == org)
    )
    customer = await db.scalar(
        select(BillingCustomer.customer_id).where(BillingCustomer.organization_id == org)
    )
    return BillingState(
        plan=sub.plan if sub else None,
        status=sub.status if sub else None,
        current_period_end=sub.current_period_end if sub else None,
        cancel_at_period_end=sub.cancel_at_period_end if sub else False,
        has_customer=customer is not None,
    )


async def checkout_url(
    db: AsyncSession,
    tenant: TenantContext,
    config: BillingConfig,
    *,
    plan: Plan,
    email: str,
    return_url: str,
) -> str:
    price = config.prices.get(plan.value)
    if price is None:
        raise BillingNotConfiguredError(plan.value)
    customer = await db.scalar(
        select(BillingCustomer.customer_id).where(
            BillingCustomer.organization_id == tenant.organization_id
        )
    )
    session = await config.provider.create_checkout(
        CheckoutRequest(
            organization_id=str(tenant.organization_id),
            price_id=price,
            customer_id=customer,
            customer_email=None if customer else email,
            success_url=f"{return_url}?checkout=done",
            cancel_url=f"{return_url}?checkout=cancelled",
            idempotency_key=f"checkout-{tenant.organization_id}-{uuid.uuid4().hex}",
        )
    )
    return session.url


async def portal_url(
    db: AsyncSession, tenant: TenantContext, config: BillingConfig, *, return_url: str
) -> str:
    customer = await db.scalar(
        select(BillingCustomer.customer_id).where(
            BillingCustomer.organization_id == tenant.organization_id
        )
    )
    if customer is None:
        raise NoCustomerError
    return await config.provider.create_portal(customer, return_url)


# --- webhooks --------------------------------------------------------------------------------


def _str(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def _uuid(value: Any) -> uuid.UUID | None:
    try:
        return uuid.UUID(str(value)) if value else None
    except ValueError:
        return None


def _when(value: Any) -> datetime | None:
    return datetime.fromtimestamp(value, tz=UTC) if isinstance(value, int | float) else None


def _subscription_fields(obj: dict[str, Any]) -> tuple[str | None, datetime | None]:
    """The price id and period end (newer API versions keep the period on the item)."""
    items = (obj.get("items") or {}).get("data") or []
    item = items[0] if items and isinstance(items[0], dict) else {}
    price = _str((item.get("price") or {}).get("id"))
    end = _when(obj.get("current_period_end")) or _when(item.get("current_period_end"))
    return price, end


class BillingWebhooks:
    def __init__(self, sessions: async_sessionmaker[AsyncSession], config: BillingConfig) -> None:
        self._sessions = sessions
        self._config = config
        self._plans = {price: Plan(plan) for plan, price in config.prices.items()}

    async def _customer_tenant(self, customer: str) -> uuid.UUID | None:
        async with self._sessions() as session, session.begin():
            await session.execute(text(f"SET LOCAL ROLE {WORKER_ROLE}"))
            found = await session.scalar(
                text("SELECT app_billing_customer_tenant(:p, :c)"),
                {"p": self._config.provider.name, "c": customer},
            )
            return uuid.UUID(str(found)) if found else None

    async def handle(self, headers: dict[str, str], body: bytes) -> str:
        """Process one webhook. Returns an outcome for the log; raises on a bad signature."""
        if len(body) > MAX_BODY_BYTES:
            raise WebhookSignatureError("too_large")
        verify(self._config.webhook_secret, headers, body)
        try:
            event = json.loads(body)
        except ValueError:
            return "unreadable"
        event_id, kind = _str(event.get("id")), _str(event.get("type"))
        obj = (event.get("data") or {}).get("object")
        if event_id is None or kind is None or not isinstance(obj, dict):
            return "unreadable"
        if kind == CHECKOUT_COMPLETED:
            return await self._checkout(event_id, kind, obj)
        if kind in SUBSCRIPTION_EVENTS:
            return await self._subscription(event_id, kind, obj, _when(event.get("created")))
        return "ignored"

    async def _bind_customer(self, session: AsyncSession, org: uuid.UUID, customer: str) -> bool:
        """Map the customer to this tenant once. False if it belongs to another tenant."""
        existing = await self._customer_tenant(customer)
        if existing is not None:
            return existing == org
        await session.execute(
            text(
                "INSERT INTO billing_customers (organization_id, provider, customer_id) "
                "VALUES (:o, :p, :c) ON CONFLICT (organization_id) DO NOTHING"
            ),
            {"o": org, "p": self._config.provider.name, "c": customer},
        )
        return True

    async def _record(self, session: AsyncSession, event_id: str, kind: str) -> bool:
        return bool(
            await session.scalar(
                text("SELECT app_billing_record_event(:e, :t)"), {"e": event_id, "t": kind}
            )
        )

    async def _checkout(self, event_id: str, kind: str, obj: dict[str, Any]) -> str:
        # Onyx set client_reference_id itself when creating the session, and Stripe signed it.
        org = _uuid(obj.get("client_reference_id")) or _uuid(
            (obj.get("metadata") or {}).get("organization_id")
        )
        customer = _str(obj.get("customer"))
        if org is None or customer is None:
            return "no_tenant"
        async with worker_transaction(self._sessions, org) as (session, _):
            if not await self._record(session, event_id, kind):
                return "duplicate"
            if not await self._bind_customer(session, org, customer):
                logger.warning("billing customer belongs to another tenant")
                return "customer_conflict"
        return "customer_linked"

    async def _subscription(
        self, event_id: str, kind: str, obj: dict[str, Any], created: datetime | None
    ) -> str:
        customer, subscription = _str(obj.get("customer")), _str(obj.get("id"))
        if customer is None or subscription is None or created is None:
            return "unreadable"
        org = await self._customer_tenant(customer)
        if org is None:
            # The subscription can arrive before its checkout event; Onyx put the tenant in the
            # subscription's metadata when creating the checkout.
            org = _uuid((obj.get("metadata") or {}).get("organization_id"))
        if org is None:
            return "no_tenant"
        status = "canceled" if kind.endswith(".deleted") else (_str(obj.get("status")) or "")
        price, period_end = _subscription_fields(obj)
        plan = self._plans.get(price) if price else None
        async with worker_transaction(self._sessions, org) as (session, tenant):
            if not await self._record(session, event_id, kind):
                return "duplicate"
            if not await self._bind_customer(session, org, customer):
                logger.warning("billing customer belongs to another tenant")
                return "customer_conflict"
            current = await session.scalar(
                select(BillingSubscription)
                .where(BillingSubscription.organization_id == org)
                .with_for_update()
            )
            if current is not None and current.last_event_at > created:
                return "stale"  # an older event arrived after a newer one
            values = {
                "provider": self._config.provider.name,
                "subscription_id": subscription,
                "plan": plan.value if plan else None,
                "price_id": price,
                "status": status,
                "current_period_end": period_end,
                "cancel_at_period_end": bool(obj.get("cancel_at_period_end")),
                "last_event_at": created,
            }
            if current is None:
                session.add(BillingSubscription(organization_id=org, **values))
            else:
                for key, value in values.items():
                    setattr(current, key, value)
                current.updated_at = datetime.now(UTC)
            await session.flush()
            await self._apply(session, tenant, plan, status)
        return f"subscription_{status}"

    async def _apply(
        self, session: AsyncSession, tenant: TenantContext, plan: Plan | None, status: str
    ) -> None:
        if status in ACTIVE_STATUSES and plan is None:
            logger.warning("billing price not mapped to a plan; modules unchanged")
            return
        if status in ACTIVE_STATUSES and plan is not None:
            spec = PLANS[plan]
            modules, budget = spec.modules, spec.ai_monthly_usd * 1_000_000
        else:
            modules, budget = BASE_MODULES, 0
        changed = await session.scalar(
            text("SELECT app_billing_apply_plan(:o, :m, :b, NULL)"),
            {"o": tenant.organization_id, "m": sorted(m.value for m in modules), "b": budget},
        )
        logger.info(
            "billing plan applied",
            extra={
                "fields": {
                    "organization_id": str(tenant.organization_id),
                    "plan": plan.value if plan else None,
                    "status": status,
                    "changed": list(changed or []),
                }
            },
        )


# --- AI usage report -------------------------------------------------------------------------


@dataclass(frozen=True)
class UsageLine:
    day: date
    workload: str
    calls: int
    input_tokens: int
    output_tokens: int
    cost_usd_micros: int


@dataclass(frozen=True)
class UsageReport:
    month: date
    lines: list[UsageLine]
    total_cost_usd_micros: int
    total_calls: int
    monthly_limit_usd_micros: int | None


def month_bounds(month: date) -> tuple[datetime, datetime]:
    """The UTC instants a month starts and the next one starts."""
    start = month.replace(day=1)
    end = date(start.year + (start.month == 12), start.month % 12 + 1, 1)
    return period_start_at(start), period_start_at(end)


async def usage_report(db: AsyncSession, tenant: TenantContext, month: date) -> UsageReport:
    """Every AI call of the month, by day and workload. Totals equal the stored events."""
    start, end = month_bounds(month)
    org = tenant.organization_id
    day = func.date_trunc("day", func.timezone("UTC", AIUsageEvent.created_at))
    rows = await db.execute(
        select(
            day.label("day"),
            AIUsageEvent.workload,
            func.count(AIUsageEvent.id),
            func.coalesce(func.sum(AIUsageEvent.input_tokens), 0),
            func.coalesce(func.sum(AIUsageEvent.output_tokens), 0),
            func.coalesce(func.sum(AIUsageEvent.cost_usd_micros), 0),
        )
        .where(
            AIUsageEvent.organization_id == org,
            AIUsageEvent.created_at >= start,
            AIUsageEvent.created_at < end,
        )
        .group_by(day, AIUsageEvent.workload)
        .order_by(day, AIUsageEvent.workload)
    )
    lines = [UsageLine(d.date(), w, int(n), int(i), int(o), int(c)) for d, w, n, i, o, c in rows]
    budget = await db.scalar(
        select(AIBudget.monthly_limit_usd_micros).where(AIBudget.organization_id == org)
    )
    return UsageReport(
        month=month.replace(day=1),
        lines=lines,
        total_cost_usd_micros=sum(line.cost_usd_micros for line in lines),
        total_calls=sum(line.calls for line in lines),
        monthly_limit_usd_micros=budget,
    )
