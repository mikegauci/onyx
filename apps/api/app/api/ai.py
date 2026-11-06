"""AI usage and budgets.

- ``GET /v1/w/{slug}/ai/usage``: the workspace's spend this month, its budget and recent
  calls, for owners and admins. Read through the app role, so RLS scopes it to the tenant.
- ``GET|PUT /v1/admin/organizations/{slug}/ai-budget``: platform admins read and set a tenant's
  monthly budget (SECURITY DEFINER functions; platform admins are not tenant members).
- ``POST /v1/admin/organizations/{slug}/ai/test-call``: platform admins run one fixed,
  harmless prompt through the gateway for a tenant, to check the configuration end to end.

Nothing here returns provider keys, configuration or prompt/reply content of real workloads.
"""

import uuid
from datetime import UTC, date, datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select, text

from app.ai.gateway import AIGateway, period_start, period_start_at
from app.ai.models import AIBudget, AIUsageEvent, UsageStatus
from app.api.admin import ADMIN_ERRORS
from app.core.auth.deps import DbDep, PlatformAdminDep, WorkspaceAccess, require_permission
from app.core.auth.permissions import Permission
from app.core.errors import (
    WORKSPACE_ERRORS,
    ErrorResponse,
    NotFoundError,
    ServiceUnavailableError,
)
from app.core.logging import request_id_var

router = APIRouter(tags=["ai"])

UsageReader = Annotated[WorkspaceAccess, require_permission(Permission.AI_USAGE_READ)]

# 10,000 USD a month is far above any pilot budget; larger values are almost certainly typos.
MAX_MONTHLY_LIMIT_USD_MICROS = 10_000 * 1_000_000

AI_CALL_ERRORS: dict[int | str, dict[str, Any]] = {
    **ADMIN_ERRORS,
    429: {"model": ErrorResponse, "description": "The tenant's AI budget is exhausted or unset"},
    503: {"model": ErrorResponse, "description": "AI unavailable or the provider failed"},
}


def get_ai_gateway(request: Request) -> AIGateway:
    gateway: AIGateway | None = getattr(request.app.state, "ai_gateway", None)
    if gateway is None:
        raise ServiceUnavailableError("AI is not configured.")
    return gateway


GatewayDep = Annotated[AIGateway, Depends(get_ai_gateway)]


# --- tenant usage ----------------------------------------------------------------------------


class AIUsageEventOut(BaseModel):
    id: uuid.UUID
    created_at: datetime
    finished_at: datetime | None
    workload: str
    provider: str
    model: str
    status: UsageStatus
    input_tokens: int
    output_tokens: int
    cost_usd_micros: int
    attempts: int
    latency_ms: int | None
    error_kind: str | None


class AIUsageSummary(BaseModel):
    period_start: date
    monthly_limit_usd_micros: int | None = Field(description="None: no budget, so AI is off.")
    alert_percent: int | None
    spent_usd_micros: int = Field(description="Includes reservations of calls in flight.")
    remaining_usd_micros: int | None
    events: list[AIUsageEventOut]


@router.get(
    "/w/{slug}/ai/usage",
    response_model=AIUsageSummary,
    responses=WORKSPACE_ERRORS,
)
async def read_ai_usage(
    workspace: UsageReader,
    db: DbDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
) -> AIUsageSummary:
    org = workspace.tenant.organization_id
    period = period_start(datetime.now(UTC))
    budget = await db.scalar(select(AIBudget).where(AIBudget.organization_id == org))
    spent = int(
        await db.scalar(
            select(func.coalesce(func.sum(AIUsageEvent.cost_usd_micros), 0)).where(
                AIUsageEvent.organization_id == org,
                AIUsageEvent.created_at >= period_start_at(period),
            )
        )
        or 0
    )
    events = (
        await db.scalars(
            select(AIUsageEvent)
            .where(AIUsageEvent.organization_id == org)
            .order_by(AIUsageEvent.created_at.desc(), AIUsageEvent.id.desc())
            .limit(limit)
        )
    ).all()
    limit_micros = budget.monthly_limit_usd_micros if budget else None
    return AIUsageSummary(
        period_start=period,
        monthly_limit_usd_micros=limit_micros,
        alert_percent=budget.alert_percent if budget else None,
        spent_usd_micros=spent,
        remaining_usd_micros=max(limit_micros - spent, 0) if limit_micros is not None else None,
        events=[AIUsageEventOut.model_validate(e, from_attributes=True) for e in events],
    )


# --- platform admin: budgets -----------------------------------------------------------------


class AIBudgetOut(BaseModel):
    slug: str
    period_start: date
    monthly_limit_usd_micros: int | None
    alert_percent: int | None
    spent_usd_micros: int


class AIBudgetUpdate(BaseModel):
    monthly_limit_usd_micros: int = Field(ge=0, le=MAX_MONTHLY_LIMIT_USD_MICROS)
    alert_percent: int = Field(default=80, ge=1, le=100)


async def _organization_id(db: DbDep, slug: str) -> uuid.UUID:
    rows = await db.execute(text("SELECT id, slug FROM app_admin_organization_summaries()"))
    found = next((row.id for row in rows if row.slug == slug), None)
    if found is None:
        raise NotFoundError("Organisation not found.")
    return uuid.UUID(str(found))


async def _budget(db: DbDep, slug: str) -> AIBudgetOut:
    await _organization_id(db, slug)
    row = (await db.execute(text("SELECT * FROM app_admin_ai_budget(:slug)"), {"slug": slug})).one()
    return AIBudgetOut(
        slug=slug,
        period_start=row.period_start,
        monthly_limit_usd_micros=row.monthly_limit_usd_micros,
        alert_percent=row.alert_percent,
        spent_usd_micros=row.spent_usd_micros,
    )


@router.get(
    "/admin/organizations/{slug}/ai-budget", response_model=AIBudgetOut, responses=ADMIN_ERRORS
)
async def read_ai_budget(slug: str, _admin: PlatformAdminDep, db: DbDep) -> AIBudgetOut:
    return await _budget(db, slug)


@router.put(
    "/admin/organizations/{slug}/ai-budget", response_model=AIBudgetOut, responses=ADMIN_ERRORS
)
async def set_ai_budget(
    slug: str, body: AIBudgetUpdate, _admin: PlatformAdminDep, db: DbDep
) -> AIBudgetOut:
    await _organization_id(db, slug)
    await db.execute(
        text("SELECT app_admin_set_ai_budget(:slug, :limit, CAST(:alert AS smallint), :rid)"),
        {
            "slug": slug,
            "limit": body.monthly_limit_usd_micros,
            "alert": body.alert_percent,
            "rid": request_id_var.get(),
        },
    )
    return await _budget(db, slug)


# --- platform admin: diagnostic call ---------------------------------------------------------

DIAGNOSTIC_WORKLOAD = "diagnostic"
DIAGNOSTIC_INSTRUCTIONS = (
    "You are a connectivity check. Reply only with the structured output requested."
)
DIAGNOSTIC_PROMPT = "Return status 'ok' and the word 'onyx' as echo."


class DiagnosticReply(BaseModel):
    status: Literal["ok"]
    echo: str = Field(max_length=50)


class AITestCallOut(BaseModel):
    reply: DiagnosticReply
    event_id: uuid.UUID
    provider: str
    model: str
    input_tokens: int
    output_tokens: int
    cost_usd_micros: int
    attempts: int
    latency_ms: int


@router.post(
    "/admin/organizations/{slug}/ai/test-call",
    response_model=AITestCallOut,
    responses=AI_CALL_ERRORS,
)
async def run_ai_test_call(
    slug: str, admin: PlatformAdminDep, db: DbDep, gateway: GatewayDep
) -> AITestCallOut:
    organization_id = await _organization_id(db, slug)
    result = await gateway.run_structured(
        organization_id=organization_id,
        workload=DIAGNOSTIC_WORKLOAD,
        output_type=DiagnosticReply,
        instructions=DIAGNOSTIC_INSTRUCTIONS,
        prompt=DIAGNOSTIC_PROMPT,
        actor_user_id=admin.id,
    )
    usage = result.usage
    return AITestCallOut(
        reply=result.output,
        event_id=usage.event_id,
        provider=usage.provider,
        model=usage.model,
        input_tokens=usage.input_tokens,
        output_tokens=usage.output_tokens,
        cost_usd_micros=usage.cost_usd_micros,
        attempts=usage.attempts,
        latency_ms=usage.latency_ms,
    )
