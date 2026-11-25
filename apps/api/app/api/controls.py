"""Pilot controls and insights for a workspace (PR-018).

- ``GET /w/{slug}/controls``: every member (the dashboard shows the manual-mode banner).
- ``PATCH /w/{slug}/controls``: owners and admins; audited with the before and after values.
- ``GET /w/{slug}/insights``: every member; counts and durations only, never message text.
"""

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert

from app.core.audit.record import record_workspace_audit
from app.core.auth.deps import DbDep, WorkspaceAccess, require_permission
from app.core.auth.permissions import Permission
from app.core.controls.models import REASON_MAX_LENGTH, WorkspaceControls
from app.core.controls.service import Controls, Feature, load_controls
from app.core.errors import WORKSPACE_ERRORS, ValidationFailedError
from app.core.insights import service as insights
from app.core.modules.models import OrganizationModule

router = APIRouter(tags=["controls"])

Reader = Annotated[WorkspaceAccess, require_permission(Permission.WORKSPACE_READ)]
Manager = Annotated[WorkspaceAccess, require_permission(Permission.WORKSPACE_UPDATE)]

EDITABLE = (
    "manual_mode",
    "manual_mode_reason",
    "assistant_enabled",
    "text_back_enabled",
    "baseline_first_reply_minutes",
    "baseline_enquiries_per_week",
)


class ControlsOut(BaseModel):
    manual_mode: bool
    manual_mode_reason: str | None
    assistant_enabled: bool
    text_back_enabled: bool
    # What actually runs: false while manual mode is on, whatever the switch says.
    assistant_active: bool
    text_back_active: bool
    baseline_first_reply_minutes: int | None
    baseline_enquiries_per_week: int | None
    updated_at: datetime | None


class ControlsUpdate(BaseModel):
    """Fields to change; omitted fields stay as they are. ``null`` clears a baseline or reason."""

    manual_mode: bool | None = None
    manual_mode_reason: str | None = Field(default=None, max_length=REASON_MAX_LENGTH)
    assistant_enabled: bool | None = None
    text_back_enabled: bool | None = None
    baseline_first_reply_minutes: int | None = Field(default=None, ge=0, le=43_200)
    baseline_enquiries_per_week: int | None = Field(default=None, ge=0, le=100_000)


NULLABLE = frozenset(
    {"manual_mode_reason", "baseline_first_reply_minutes", "baseline_enquiries_per_week"}
)


def _out(c: Controls) -> ControlsOut:
    return ControlsOut(
        manual_mode=c.manual_mode,
        manual_mode_reason=c.manual_mode_reason,
        assistant_enabled=c.assistant_enabled,
        text_back_enabled=c.text_back_enabled,
        assistant_active=c.feature_on(Feature.ASSISTANT),
        text_back_active=c.feature_on(Feature.TEXT_BACK),
        baseline_first_reply_minutes=c.baseline_first_reply_minutes,
        baseline_enquiries_per_week=c.baseline_enquiries_per_week,
        updated_at=c.updated_at,
    )


@router.get("/w/{slug}/controls", response_model=ControlsOut, responses=WORKSPACE_ERRORS)
async def read_controls(workspace: Reader, db: DbDep) -> ControlsOut:
    return _out(await load_controls(db, workspace.tenant.organization_id))


@router.patch("/w/{slug}/controls", response_model=ControlsOut, responses=WORKSPACE_ERRORS)
async def update_controls(body: ControlsUpdate, workspace: Manager, db: DbDep) -> ControlsOut:
    org = workspace.tenant.organization_id
    before = await load_controls(db, org)
    sent = body.model_dump(exclude_unset=True)
    sent = {k: v for k, v in sent.items() if v is not None or k in NULLABLE}
    if sent.get("manual_mode") is False:
        sent["manual_mode_reason"] = None  # a reason only explains manual mode while it is on
    changes = {k: v for k, v in sent.items() if getattr(before, k) != v}
    if not changes:
        return _out(before)
    values = {k: getattr(before, k) for k in EDITABLE} | changes
    await db.execute(
        insert(WorkspaceControls)
        .values(organization_id=org, updated_by_user_id=workspace.user.id, **values)
        .on_conflict_do_update(
            index_elements=[WorkspaceControls.organization_id],
            set_={**changes, "updated_by_user_id": workspace.user.id, "updated_at": func.now()},
        )
    )
    await record_workspace_audit(
        db,
        workspace,
        action="workspace.controls.updated",
        target_type="organization",
        target_id=org,
        details={
            "before": {k: getattr(before, k) for k in changes if k != "manual_mode_reason"},
            "after": {k: v for k, v in changes.items() if k != "manual_mode_reason"},
        },
    )
    return _out(await load_controls(db, org))


# --- insights ----------------------------------------------------------------------------------


class Count(BaseModel):
    key: str
    count: int


class EnquiriesOut(BaseModel):
    total: int
    by_channel: list[Count]


class ResponseTimeOut(BaseModel):
    answered: int
    unanswered: int
    median_seconds: int | None
    p90_seconds: int | None
    automatic_replies: int


class DraftsOut(BaseModel):
    total: int
    sent_as_written: int
    sent_after_edit: int
    rejected: int
    expired: int
    waiting: int
    superseded: int
    median_approval_seconds: int | None


class RunsOut(BaseModel):
    total: int
    drafted: int
    escalated: int
    top_reasons: list[Count]


class QuotesOut(BaseModel):
    created: int
    approved: int
    sent: int
    accepted: int


class MissedCallsOut(BaseModel):
    total: int
    whatsapp_sent: int
    sms_sent: int
    skipped: int
    failed: int
    skip_reasons: list[Count]


class DealsOut(BaseModel):
    created: int
    sold: int
    collected: int
    cancelled: int
    open_now: int
    customer_uploads: int


class FinanceOut(BaseModel):
    started: int
    by_assistant: int
    approved: int
    declined: int
    open_now: int


class BaselineOut(BaseModel):
    first_reply_minutes: int | None
    enquiries_per_week: int | None


class InsightsOut(BaseModel):
    days: int
    since: datetime
    baseline: BaselineOut
    enquiries: EnquiriesOut | None
    response_time: ResponseTimeOut | None
    drafts: DraftsOut | None
    runs: RunsOut | None
    quotes: QuotesOut | None
    missed_calls: MissedCallsOut | None
    deals: DealsOut | None = None
    finance: FinanceOut | None = None


def _counts(pairs: list[tuple[str, int]]) -> list[Count]:
    return [Count(key=k, count=n) for k, n in pairs]


@router.get("/w/{slug}/insights", response_model=InsightsOut, responses=WORKSPACE_ERRORS)
async def read_insights(
    workspace: Reader,
    db: DbDep,
    days: Annotated[int, Query(description="7, 30 or 90")] = 30,
) -> InsightsOut:
    if days not in insights.ALLOWED_DAYS:
        raise ValidationFailedError("Choose 7, 30 or 90 days.")
    org = workspace.tenant.organization_id
    modules = frozenset(
        await db.scalars(
            select(OrganizationModule.module_key).where(
                OrganizationModule.organization_id == org, OrganizationModule.enabled
            )
        )
    )
    data = await insights.build(db, org, days=days, now=datetime.now(UTC), modules=modules)
    controls = await load_controls(db, org)
    return InsightsOut(
        days=data.days,
        since=data.since,
        baseline=BaselineOut(
            first_reply_minutes=controls.baseline_first_reply_minutes,
            enquiries_per_week=controls.baseline_enquiries_per_week,
        ),
        enquiries=(
            EnquiriesOut(
                total=data.enquiries.total,
                by_channel=_counts(list(data.enquiries.by_channel.items())),
            )
            if data.enquiries
            else None
        ),
        response_time=(ResponseTimeOut(**vars(data.response_time)) if data.response_time else None),
        drafts=DraftsOut(**vars(data.drafts)) if data.drafts else None,
        runs=(
            RunsOut(
                total=data.runs.total,
                drafted=data.runs.drafted,
                escalated=data.runs.escalated,
                top_reasons=_counts(data.runs.top_reasons),
            )
            if data.runs
            else None
        ),
        quotes=QuotesOut(**vars(data.quotes)) if data.quotes else None,
        missed_calls=(
            MissedCallsOut(
                total=data.missed_calls.total,
                whatsapp_sent=data.missed_calls.whatsapp_sent,
                sms_sent=data.missed_calls.sms_sent,
                skipped=data.missed_calls.skipped,
                failed=data.missed_calls.failed,
                skip_reasons=_counts(data.missed_calls.skip_reasons),
            )
            if data.missed_calls
            else None
        ),
        deals=DealsOut(**vars(data.deals)) if data.deals else None,
        finance=FinanceOut(**vars(data.finance)) if data.finance else None,
    )
