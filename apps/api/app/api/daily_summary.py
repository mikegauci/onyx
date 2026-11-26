"""Daily owner summary (VA-010).

- ``GET`` / ``PUT /w/{slug}/insights/daily-summary/settings``: owners and admins.
- ``GET /w/{slug}/insights/daily-summary/preview``: today's figures so far; every member.
- ``POST /w/{slug}/insights/daily-summary/test``: sends today's preview to the caller only.
- ``GET /w/{slug}/insights/daily-summary/history``: the last 30 days sent; every member.

Figures are counts and amounts only, never names, numbers or message text.
"""

import secrets
import uuid
from datetime import date, datetime, time
from typing import Annotated, Literal

from fastapi import APIRouter
from pydantic import BaseModel, Field, StringConstraints

from app.core.audit.record import record_workspace_audit
from app.core.auth.deps import DbDep, WorkspaceAccess, require_permission
from app.core.auth.permissions import Permission
from app.core.errors import WORKSPACE_ERRORS, ErrorDetail, ValidationFailedError
from app.core.insights import daily, summary
from app.modules.inbox import public as inbox

router = APIRouter(prefix="/w/{slug}/insights/daily-summary", tags=["insights"])

Reader = Annotated[WorkspaceAccess, require_permission(Permission.WORKSPACE_READ)]
Manager = Annotated[WorkspaceAccess, require_permission(Permission.WORKSPACE_UPDATE)]
Phone = Annotated[str, StringConstraints(strip_whitespace=True, pattern=r"^\+[1-9]\d{6,14}$")]


class SummaryRecipientIn(BaseModel):
    user_id: uuid.UUID
    email: bool = True
    whatsapp: Phone | None = None


class SummaryRecipientOut(SummaryRecipientIn):
    display_name: str | None
    email_address: str | None


class SummaryMemberOut(BaseModel):
    user_id: uuid.UUID
    display_name: str
    email: str


class SummarySettingsIn(BaseModel):
    enabled: bool
    send_at: time = time(19, 0)
    recipients: list[SummaryRecipientIn] = Field(
        default_factory=list, max_length=summary.MAX_RECIPIENTS
    )
    template_id: uuid.UUID | None = None
    params: list[Literal["workspace", "date", "summary"]] = Field(
        default_factory=list, max_length=3
    )


class SummarySettingsOut(BaseModel):
    enabled: bool
    send_at: time
    recipients: list[SummaryRecipientOut]
    template_id: uuid.UUID | None
    template_ready: bool
    params: list[str]
    members: list[SummaryMemberOut]
    timezone: str
    updated_at: datetime | None


class SummaryEnquiriesOut(BaseModel):
    total: int
    by_channel: dict[str, int]
    missed_calls: int


class SummaryDealsOut(BaseModel):
    reserved: int
    sold: int


class SummaryPaymentsOut(BaseModel):
    count: int
    total_cents: int


class SummaryListingsOut(BaseModel):
    added: int
    removed: int
    available: int


class SummaryFiguresOut(BaseModel):
    day: date
    enquiries: SummaryEnquiriesOut | None
    deals: SummaryDealsOut | None
    payments: SummaryPaymentsOut | None
    listings: SummaryListingsOut | None
    # Sections without a source: "not_set_up" (module off) or "not_connected".
    missing: dict[str, str]


class SummaryPreviewOut(BaseModel):
    figures: SummaryFiguresOut
    text: str


class SummarySendResultOut(BaseModel):
    user_id: uuid.UUID | None
    channel: str
    status: str  # sent, skipped or failed
    reason: str | None


class SummaryTestOut(BaseModel):
    results: list[SummarySendResultOut]


class SummaryHistoryItem(BaseModel):
    id: uuid.UUID
    summary_date: date
    status: str  # sending, sent, partly_sent or failed
    text: str
    results: list[SummarySendResultOut]
    sent_at: datetime | None


class SummaryHistoryOut(BaseModel):
    items: list[SummaryHistoryItem]


def _invalid(field: str, message: str) -> ValidationFailedError:
    return ValidationFailedError(
        message, details=[ErrorDetail(loc=["body", field], msg=message, type="invalid")]
    )


def _figures(f: daily.Figures) -> SummaryFiguresOut:
    return SummaryFiguresOut.model_validate(f.to_json())


def _results(items: list[dict[str, object]]) -> list[SummarySendResultOut]:
    return [SummarySendResultOut.model_validate(r) for r in items]


async def _settings_out(db: DbDep, workspace: WorkspaceAccess) -> SummarySettingsOut:
    org = workspace.tenant.organization_id
    settings = await summary.load_settings(db, org)
    people = await summary.members(db)
    by_id = {m.user_id: m for m in people}
    ready = False
    if settings.template_id is not None:
        template = await inbox.whatsapp_template(db, workspace.tenant, settings.template_id)
        ready = bool(
            template
            and template.usable_for_utility
            and template.param_count == len(settings.params)
        )
    recipients = []
    for r in settings.recipients:
        member = by_id.get(uuid.UUID(str(r["user_id"])))
        recipients.append(
            SummaryRecipientOut(
                user_id=r["user_id"],
                email=bool(r.get("email")),
                whatsapp=r.get("whatsapp"),
                display_name=member.display_name if member else None,
                email_address=member.email if member else None,
            )
        )
    return SummarySettingsOut(
        enabled=settings.enabled,
        send_at=settings.send_at,
        recipients=recipients,
        template_id=settings.template_id,
        template_ready=ready,
        params=list(settings.params),
        members=[SummaryMemberOut(**vars(m)) for m in people],
        timezone=workspace.organization.timezone,
        updated_at=getattr(settings, "updated_at", None),
    )


@router.get("/settings", response_model=SummarySettingsOut, responses=WORKSPACE_ERRORS)
async def read_summary_settings(workspace: Manager, db: DbDep) -> SummarySettingsOut:
    return await _settings_out(db, workspace)


@router.put("/settings", response_model=SummarySettingsOut, responses=WORKSPACE_ERRORS)
async def update_summary_settings(
    body: SummarySettingsIn, workspace: Manager, db: DbDep
) -> SummarySettingsOut:
    org = workspace.tenant.organization_id
    member_ids = {m.user_id for m in await summary.members(db)}
    seen: set[uuid.UUID] = set()
    for r in body.recipients:
        if r.user_id not in member_ids:
            raise _invalid("recipients", "Each recipient must be a member of this workspace.")
        if r.user_id in seen:
            raise _invalid("recipients", "Each member can only be listed once.")
        if not r.email and not r.whatsapp:
            raise _invalid("recipients", "Choose email, WhatsApp or both for each recipient.")
        seen.add(r.user_id)
    if body.enabled and not body.recipients:
        raise _invalid("recipients", "Add at least one recipient to turn the summary on.")
    if body.template_id is not None:
        template = await inbox.whatsapp_template(db, workspace.tenant, body.template_id)
        if template is None or not template.usable_for_utility:
            raise _invalid("template_id", "Choose an approved WhatsApp utility template.")
        if template.param_count != len(body.params):
            raise _invalid("params", f"This template needs {template.param_count} value(s).")
    send_at = body.send_at.replace(second=0, microsecond=0, tzinfo=None)
    values = {
        "enabled": body.enabled,
        "send_at": send_at,
        "recipients": [r.model_dump(mode="json") for r in body.recipients],
        "template_id": body.template_id,
        "params": list(body.params) if body.template_id else [],
    }
    await summary.save_settings(db, org, workspace.user.id, values)
    await record_workspace_audit(
        db,
        workspace,
        action="insights.daily_summary.updated",
        target_type="organization",
        target_id=org,
        details={
            "enabled": body.enabled,
            "send_at": send_at.isoformat(timespec="minutes"),
            "recipients": len(body.recipients),
            "whatsapp": sum(1 for r in body.recipients if r.whatsapp),
        },
    )
    return await _settings_out(db, workspace)


async def _today(db: DbDep, workspace: WorkspaceAccess) -> daily.Figures:
    zone = daily.zone_of(workspace.organization.timezone)
    day = datetime.now(zone).date()
    return await summary.collect(db, workspace.tenant.organization_id, day, zone)


@router.get("/preview", response_model=SummaryPreviewOut, responses=WORKSPACE_ERRORS)
async def preview_summary(workspace: Reader, db: DbDep) -> SummaryPreviewOut:
    figures = await _today(db, workspace)
    return SummaryPreviewOut(
        figures=_figures(figures), text=daily.render(workspace.organization.name, figures)
    )


@router.post("/test", response_model=SummaryTestOut, responses=WORKSPACE_ERRORS)
async def send_test_summary(workspace: Manager, db: DbDep) -> SummaryTestOut:
    """Today's preview to the caller only: their recipient channels, or email if not listed."""
    settings = await summary.load_settings(db, workspace.tenant.organization_id)
    me = str(workspace.user.id)
    mine = [r for r in settings.recipients if str(r.get("user_id")) == me] or [
        {"user_id": me, "email": True, "whatsapp": None}
    ]
    figures = await _today(db, workspace)
    results = await summary.send_all(
        db,
        workspace.tenant,
        settings=settings,
        recipients=mine,
        name=workspace.organization.name,
        figures=figures,
        key=f"summary-test:{secrets.token_hex(8)}",
    )
    await record_workspace_audit(
        db,
        workspace,
        action="insights.daily_summary.test_sent",
        target_type="organization",
        target_id=workspace.tenant.organization_id,
        details={"sent": sum(r["status"] == "sent" for r in results), "sends": len(results)},
    )
    return SummaryTestOut(results=_results(results))


@router.get("/history", response_model=SummaryHistoryOut, responses=WORKSPACE_ERRORS)
async def read_summary_history(workspace: Reader, db: DbDep) -> SummaryHistoryOut:
    rows = await summary.history(db, workspace.tenant.organization_id)
    return SummaryHistoryOut(
        items=[
            SummaryHistoryItem(
                id=r.id,
                summary_date=r.summary_date,
                status=r.status,
                text=r.body,
                results=_results(r.results),
                sent_at=r.sent_at,
            )
            for r in rows
        ]
    )
