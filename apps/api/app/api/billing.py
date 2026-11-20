"""Billing for a workspace (PR-026): the plan, checkout and portal links, AI usage report.

Owners change plans and payment details (``billing.manage``); admins see the plan and the
usage report (``billing.read``). Return links must be on an allowed dashboard origin, so a
checkout cannot send people to another site.
"""

import csv
import io
from datetime import UTC, date, datetime
from typing import Annotated
from urllib.parse import urlparse

from fastapi import APIRouter, Query, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field

from app.core.auth.deps import DbDep, WorkspaceAccess, require_permission
from app.core.auth.permissions import Permission
from app.core.billing import service
from app.core.billing.plans import PLANS, Plan
from app.core.errors import (
    WORKSPACE_ERRORS,
    ConflictError,
    ErrorDetail,
    ServiceUnavailableError,
    ValidationFailedError,
)
from app.integrations.billing import BillingConfig, BillingProviderError

router = APIRouter(tags=["billing"])

ReadBilling = Annotated[WorkspaceAccess, require_permission(Permission.BILLING_READ)]
ManageBilling = Annotated[WorkspaceAccess, require_permission(Permission.BILLING_MANAGE)]


class PlanOut(BaseModel):
    key: Plan
    name: str
    modules: list[str]
    ai_monthly_usd: int
    available: bool  # a price is configured for it


class BillingOut(BaseModel):
    configured: bool
    plan: str | None
    status: str | None
    current_period_end: datetime | None
    cancel_at_period_end: bool
    has_customer: bool
    plans: list[PlanOut]


class CheckoutIn(BaseModel):
    plan: Plan
    return_url: str = Field(max_length=2000)


class PortalIn(BaseModel):
    return_url: str = Field(max_length=2000)


class LinkOut(BaseModel):
    url: str


class UsageLineOut(BaseModel):
    day: date
    workload: str
    calls: int
    input_tokens: int
    output_tokens: int
    cost_usd_micros: int


class UsageReportOut(BaseModel):
    month: date
    lines: list[UsageLineOut]
    total_calls: int
    total_cost_usd_micros: int
    monthly_limit_usd_micros: int | None


def _config(request: Request) -> BillingConfig | None:
    config: BillingConfig | None = getattr(request.app.state, "billing_config", None)
    return config


def _return_url(request: Request, url: str) -> str:
    origins = set(request.app.state.settings.cors_origins)
    parsed = urlparse(url)
    if f"{parsed.scheme}://{parsed.netloc}" not in origins or parsed.scheme not in (
        "https",
        "http",
    ):
        raise ValidationFailedError(
            "The return link must be on the Onyx dashboard.",
            details=[ErrorDetail(loc=["body", "return_url"], msg="Not allowed.", type="origin")],
        )
    return f"{parsed.scheme}://{parsed.netloc}{parsed.path}"


@router.get("/w/{slug}/billing", response_model=BillingOut, responses=WORKSPACE_ERRORS)
async def read_billing(request: Request, workspace: ReadBilling, db: DbDep) -> BillingOut:
    config = _config(request)
    current = await service.state(db, workspace.tenant)
    return BillingOut(
        configured=config is not None,
        plan=current.plan,
        status=current.status,
        current_period_end=current.current_period_end,
        cancel_at_period_end=current.cancel_at_period_end,
        has_customer=current.has_customer,
        plans=[
            PlanOut(
                key=spec.key,
                name=spec.name,
                modules=sorted(m.value for m in spec.modules),
                ai_monthly_usd=spec.ai_monthly_usd,
                available=config is not None and spec.key.value in config.prices,
            )
            for spec in PLANS.values()
        ],
    )


def _require(request: Request) -> BillingConfig:
    config = _config(request)
    if config is None:
        raise ServiceUnavailableError("Billing is not set up yet.")
    return config


@router.post("/w/{slug}/billing/checkout", response_model=LinkOut, responses=WORKSPACE_ERRORS)
async def start_checkout(
    body: CheckoutIn, request: Request, workspace: ManageBilling, db: DbDep
) -> LinkOut:
    config = _require(request)
    try:
        url = await service.checkout_url(
            db,
            workspace.tenant,
            config,
            plan=body.plan,
            email=workspace.user.email,
            return_url=_return_url(request, body.return_url),
        )
    except service.BillingNotConfiguredError as exc:
        raise ConflictError("That plan is not available yet.") from exc
    except BillingProviderError as exc:
        raise ServiceUnavailableError("The payment provider is unavailable. Try again.") from exc
    return LinkOut(url=url)


@router.post("/w/{slug}/billing/portal", response_model=LinkOut, responses=WORKSPACE_ERRORS)
async def open_portal(
    body: PortalIn, request: Request, workspace: ManageBilling, db: DbDep
) -> LinkOut:
    config = _require(request)
    try:
        url = await service.portal_url(
            db, workspace.tenant, config, return_url=_return_url(request, body.return_url)
        )
    except service.NoCustomerError as exc:
        raise ConflictError("Choose a plan first; the billing portal opens after that.") from exc
    except BillingProviderError as exc:
        raise ServiceUnavailableError("The payment provider is unavailable. Try again.") from exc
    return LinkOut(url=url)


def usd(micros: int) -> str:
    """Millionths of a dollar as an exact decimal string (no floats for money)."""
    sign = "-" if micros < 0 else ""
    whole, part = divmod(abs(micros), 1_000_000)
    return f"{sign}{whole}.{part:06d}"


Month = Annotated[str | None, Query(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")]


def _month(value: str | None) -> date:
    if value is None:
        return datetime.now(UTC).date().replace(day=1)
    year, month = value.split("-")
    return date(int(year), int(month), 1)


@router.get("/w/{slug}/billing/usage", response_model=UsageReportOut, responses=WORKSPACE_ERRORS)
async def usage(workspace: ReadBilling, db: DbDep, month: Month = None) -> UsageReportOut:
    report = await service.usage_report(db, workspace.tenant, _month(month))
    return UsageReportOut(
        month=report.month,
        lines=[UsageLineOut(**line.__dict__) for line in report.lines],
        total_calls=report.total_calls,
        total_cost_usd_micros=report.total_cost_usd_micros,
        monthly_limit_usd_micros=report.monthly_limit_usd_micros,
    )


@router.get("/w/{slug}/billing/usage.csv", responses=WORKSPACE_ERRORS)
async def usage_csv(workspace: ReadBilling, db: DbDep, month: Month = None) -> Response:
    report = await service.usage_report(db, workspace.tenant, _month(month))
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["day", "workload", "calls", "input_tokens", "output_tokens", "cost_usd"])
    for line in report.lines:
        writer.writerow(
            [
                line.day.isoformat(),
                line.workload,
                line.calls,
                line.input_tokens,
                line.output_tokens,
                usd(line.cost_usd_micros),
            ]
        )
    writer.writerow(["total", "", report.total_calls, "", "", usd(report.total_cost_usd_micros)])
    filename = f"onyx-ai-usage-{report.month:%Y-%m}.csv"
    return Response(
        out.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
