"""Onyx plans: what each includes. Prices live in Stripe; the owner sets them there.

These are placeholders until the owner decides the commercial plans. A plan's modules must
include what each module requires (checked by ``tests/test_billing_plans.py``).
"""

import enum
from dataclasses import dataclass

from app.core.modules.registry import ModuleKey


class Plan(enum.StrEnum):
    STARTER = "starter"
    GROWTH = "growth"


@dataclass(frozen=True)
class PlanSpec:
    key: Plan
    name: str
    modules: frozenset[ModuleKey]
    ai_monthly_usd: int  # the AI budget the plan includes, in US dollars


PLANS: dict[Plan, PlanSpec] = {
    Plan.STARTER: PlanSpec(
        Plan.STARTER,
        "Starter",
        frozenset({ModuleKey.CRM, ModuleKey.INBOX}),
        ai_monthly_usd=0,
    ),
    Plan.GROWTH: PlanSpec(
        Plan.GROWTH,
        "Growth",
        frozenset(
            {
                ModuleKey.CRM,
                ModuleKey.INBOX,
                ModuleKey.CATALOGUE,
                ModuleKey.QUOTATIONS,
                ModuleKey.OUTBOUND,
                ModuleKey.ASSISTANT,
                ModuleKey.KNOWLEDGE,
                ModuleKey.AUTOMOTIVE,
                ModuleKey.DEALS,
            }
        ),
        ai_monthly_usd=50,
    ),
}

# Without an active subscription a tenant keeps these, so its customers' conversations stay
# reachable while it sorts out billing.
BASE_MODULES = frozenset({ModuleKey.CRM, ModuleKey.INBOX})

# Stripe subscription statuses that keep a plan's modules on.
ACTIVE_STATUSES = frozenset({"active", "trialing", "past_due"})
