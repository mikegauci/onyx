"""Google review requests (VA-009 part 1).

- The workspace sets its Google review link, how many days after collection to ask, the
  message and, optionally, an approved WhatsApp **utility** template. No link: nothing is due.
- The scheduler (``create_due``) adds one pending request per deal collected at least the delay
  ago (and at most 30 days past that, so turning the feature on does not ask old customers).
  The unique deal id means one request per sale, however often it runs.
- Nothing sends automatically. Staff send requests (one or several at once). Each send, in its
  own savepoint, tries WhatsApp first: free-form text inside the 24-hour window, else the
  template. It falls back to email. Opted-out or suppressed addresses are refused by the inbox,
  and the request is skipped with the reason. The idempotency key ``review-{id}`` makes a retry
  send nothing new.
"""

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from typing import Annotated
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit.record import record_workspace_audit
from app.core.auth.deps import WorkspaceAccess
from app.core.db.context import TenantContext
from app.core.errors import (
    AppError,
    ConflictError,
    ErrorDetail,
    NotFoundError,
    ValidationFailedError,
)
from app.modules.crm import public as crm
from app.modules.deals.models import (
    Deal,
    ReviewChannel,
    ReviewRequest,
    ReviewSettings,
    ReviewStatus,
)
from app.modules.inbox import public as inbox

MAX_SEND = 50
CATCH_UP = timedelta(days=30)
PARAM_KEYS = ("first_name", "vehicle", "link")
GOOGLE_HOSTS = ("g.page", "google.com", "goo.gl", "maps.app.goo.gl", "search.google.com")
DEFAULT_SUBJECT = "How was your experience with {workspace}?"
DEFAULT_MESSAGE = (
    "Hi {name}, thank you for choosing us for your {car}. If you have a minute, a Google "
    "review would help us a lot: {link}"
)
Text200 = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
Text1000 = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)]


# --- schemas ---------------------------------------------------------------------------------


class _Input(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ReviewSettingsIn(_Input):
    google_review_url: str | None = Field(
        default=None, max_length=500, description="The Google review link; null turns it off"
    )
    delay_days: int = Field(default=7, ge=1, le=60)
    email_subject: Text200 | None = None
    message: Text1000 | None = Field(
        default=None, description="Email and free-form WhatsApp text: {name}, {car} and {link}"
    )
    template_id: uuid.UUID | None = Field(
        default=None, description="An approved WhatsApp utility template, used outside 24h"
    )
    params: list[str] = Field(
        default_factory=list,
        max_length=10,
        description=f"What fills each template value, in order: {', '.join(PARAM_KEYS)}",
    )

    @field_validator("google_review_url")
    @classmethod
    def _google(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return None
        value = value.strip()
        parsed = urlparse(value)
        host = (parsed.hostname or "").lower()
        if parsed.scheme != "https" or not any(
            host == h or host.endswith(f".{h}") for h in GOOGLE_HOSTS
        ):
            raise ValueError("Use the https review link from your Google Business Profile.")
        return value

    @field_validator("message")
    @classmethod
    def _has_link(cls, value: str | None) -> str | None:
        if value is not None and "{link}" not in value:
            raise ValueError("The message must contain {link}.")
        return value


class ReviewSettingsOut(BaseModel):
    google_review_url: str | None
    delay_days: int
    email_subject: str
    message: str
    template_id: uuid.UUID | None
    template_name: str | None
    template_body: str | None
    params: list[str]
    param_keys: list[str]
    enabled: bool = Field(description="A Google review link is set, so requests are created")
    template_ready: bool = Field(description="A usable template is chosen for outside 24h")


class ReviewRequestOut(BaseModel):
    id: uuid.UUID
    deal_id: uuid.UUID
    deal_title: str
    contact_id: uuid.UUID
    contact_name: str
    has_phone: bool
    has_email: bool
    status: ReviewStatus
    channel: ReviewChannel | None
    skip_reason: str | None
    collected_at: datetime | None
    created_at: datetime
    decided_at: datetime | None


class ReviewRequestList(BaseModel):
    items: list[ReviewRequestOut]
    total: int


class ReviewSendRequest(_Input):
    request_ids: list[uuid.UUID] = Field(min_length=1, max_length=MAX_SEND)


class ReviewSkip(BaseModel):
    request_id: uuid.UUID
    reason: str
    message: str


class ReviewSendResult(BaseModel):
    sent: list[uuid.UUID]
    skipped: list[ReviewSkip]


SKIP_TEXT = {
    "not_found": "Review request not found.",
    "already_decided": "This review request was already sent or dismissed.",
    "not_set_up": "Add the Google review link in Settings first.",
    "no_channel": "The customer has no WhatsApp conversation or email address to send to.",
    "cannot_send": "The message could not be sent.",
    "send_failed": "The provider did not accept the message. Try again later.",
}


def _skip(request_id: uuid.UUID, reason: str, message: str | None = None) -> ReviewSkip:
    return ReviewSkip(request_id=request_id, reason=reason, message=message or SKIP_TEXT[reason])


def _first_name(full_name: str) -> str:
    parts = full_name.split()
    return parts[0] if parts else "there"


def render(template: str, *, name: str, car: str, link: str, workspace: str = "") -> str:
    """Fill {name}, {car}, {link} and {workspace}; any other brace text stays as written."""
    out = template
    for key, value in (("name", name), ("car", car), ("link", link), ("workspace", workspace)):
        out = out.replace("{" + key + "}", value)
    return out


# --- scheduler -------------------------------------------------------------------------------


async def create_due(db: AsyncSession, tenant: TenantContext, now: datetime) -> int:
    """Add a pending request for each deal collected ``delay_days`` ago (within the catch-up
    window) that has none. Idempotent. Runs as the worker. Returns how many were added."""
    settings = await db.scalar(
        select(ReviewSettings).where(ReviewSettings.organization_id == tenant.organization_id)
    )
    if settings is None or not settings.google_review_url:
        return 0
    due_before = now - timedelta(days=settings.delay_days)
    result = await db.execute(
        text(
            "INSERT INTO deal_review_requests (organization_id, deal_id, contact_id, status) "
            "SELECT d.organization_id, d.id, d.contact_id, 'pending' FROM deals d "
            "WHERE d.organization_id = :org AND d.stage = 'collected' "
            "AND d.closed_at <= :due AND d.closed_at > :since "
            "ON CONFLICT ON CONSTRAINT uq_deal_review_requests_deal DO NOTHING"
        ),
        {
            "org": tenant.organization_id,
            "due": due_before,
            "since": due_before - CATCH_UP,
        },
    )
    return int(getattr(result, "rowcount", 0) or 0)


# --- the service -----------------------------------------------------------------------------


class ReviewService:
    def __init__(self, db: AsyncSession, workspace: WorkspaceAccess) -> None:
        self.db = db
        self.workspace = workspace
        self.tenant = workspace.tenant
        self.org = workspace.tenant.organization_id

    # --- settings --------------------------------------------------------------------------

    async def _settings_row(self) -> ReviewSettings | None:
        return await self.db.scalar(
            select(ReviewSettings).where(ReviewSettings.organization_id == self.org)
        )

    async def settings(self) -> ReviewSettingsOut:
        row = await self._settings_row()
        template = (
            await inbox.whatsapp_template(self.db, self.tenant, row.template_id)
            if row is not None and row.template_id is not None
            else None
        )
        params = list(row.params) if row is not None else []
        return ReviewSettingsOut(
            google_review_url=row.google_review_url if row else None,
            delay_days=row.delay_days if row else 7,
            email_subject=(row.email_subject if row and row.email_subject else DEFAULT_SUBJECT),
            message=(row.message if row and row.message else DEFAULT_MESSAGE),
            template_id=template.id if template else None,
            template_name=template.name if template else None,
            template_body=template.body if template else None,
            params=params,
            param_keys=list(PARAM_KEYS),
            enabled=bool(row and row.google_review_url),
            template_ready=bool(
                template and template.usable_for_utility and len(params) == template.param_count
            ),
        )

    async def update_settings(self, body: ReviewSettingsIn) -> ReviewSettingsOut:
        if body.template_id is not None:
            template = await inbox.whatsapp_template(self.db, self.tenant, body.template_id)
            if template is None or not template.usable_for_utility:
                raise ValidationFailedError(
                    "Choose an approved, supported WhatsApp utility template.",
                    details=[
                        ErrorDetail(loc=["body", "template_id"], msg="not usable", type="template")
                    ],
                )
            if len(body.params) != template.param_count or any(
                p not in PARAM_KEYS for p in body.params
            ):
                raise ValidationFailedError(
                    f"The template has {template.param_count} values; fill each with one of "
                    f"{', '.join(PARAM_KEYS)}.",
                    details=[ErrorDetail(loc=["body", "params"], msg="mismatch", type="params")],
                )
        row = await self._settings_row()
        if row is None:
            row = ReviewSettings(organization_id=self.org)
            self.db.add(row)
        row.google_review_url = body.google_review_url
        row.delay_days = body.delay_days
        row.email_subject = body.email_subject
        row.message = body.message
        row.template_id = body.template_id
        row.params = list(body.params) if body.template_id else []
        row.updated_by_user_id = self.workspace.user.id
        row.updated_at = datetime.now(UTC)
        await self.db.flush()
        await record_workspace_audit(
            self.db,
            self.workspace,
            action="deals.reviews.settings_updated",
            target_type="deal_review_settings",
            target_id=self.org,
            details={
                "enabled": body.google_review_url is not None,
                "delay_days": body.delay_days,
                "template_id": str(body.template_id) if body.template_id else None,
            },
        )
        return await self.settings()

    # --- the list --------------------------------------------------------------------------

    async def _out(self, rows: Sequence[ReviewRequest]) -> list[ReviewRequestOut]:
        if not rows:
            return []
        deals = {
            d.id: d
            for d in (
                await self.db.scalars(
                    select(Deal).where(
                        Deal.organization_id == self.org, Deal.id.in_({r.deal_id for r in rows})
                    )
                )
            ).all()
        }
        contacts = await crm.get_contacts(self.db, self.tenant, {r.contact_id for r in rows})
        out = []
        for r in rows:
            contact = contacts.get(r.contact_id)
            deal = deals.get(r.deal_id)
            out.append(
                ReviewRequestOut(
                    id=r.id,
                    deal_id=r.deal_id,
                    deal_title=deal.title if deal else "Deal",
                    contact_id=r.contact_id,
                    contact_name=contact.full_name if contact else "Unknown",
                    has_phone=bool(contact and contact.phone),
                    has_email=bool(contact and contact.email),
                    status=ReviewStatus(r.status),
                    channel=ReviewChannel(r.channel) if r.channel else None,
                    skip_reason=r.skip_reason,
                    collected_at=deal.closed_at if deal else None,
                    created_at=r.created_at,
                    decided_at=r.decided_at,
                )
            )
        return out

    async def list(self, status: ReviewStatus | None, limit: int, offset: int) -> ReviewRequestList:
        conditions = [ReviewRequest.organization_id == self.org]
        if status is not None:
            conditions.append(ReviewRequest.status == status.value)
        total = await self.db.scalar(
            select(func.count()).select_from(ReviewRequest).where(*conditions)
        )
        rows = (
            await self.db.scalars(
                select(ReviewRequest)
                .where(*conditions)
                .order_by(ReviewRequest.created_at.desc(), ReviewRequest.id)
                .limit(limit)
                .offset(offset)
            )
        ).all()
        return ReviewRequestList(items=await self._out(rows), total=total or 0)

    async def _row(self, request_id: uuid.UUID) -> ReviewRequest | None:
        return await self.db.scalar(
            select(ReviewRequest)
            .where(ReviewRequest.organization_id == self.org, ReviewRequest.id == request_id)
            .with_for_update()
        )

    async def dismiss(self, request_id: uuid.UUID) -> ReviewRequestOut:
        row = await self._row(request_id)
        if row is None:
            raise NotFoundError("Review request not found.")
        if row.status == ReviewStatus.SENT.value:
            raise ConflictError("This review request was already sent.")
        row.status = ReviewStatus.DISMISSED.value
        row.skip_reason = None
        row.decided_by_user_id = self.workspace.user.id
        row.decided_at = datetime.now(UTC)
        row.updated_at = row.decided_at
        await self.db.flush()
        await record_workspace_audit(
            self.db,
            self.workspace,
            action="deals.review.dismissed",
            target_type="deal_review_request",
            target_id=row.id,
        )
        return (await self._out([row]))[0]

    # --- sending ---------------------------------------------------------------------------

    async def send(self, body: ReviewSendRequest) -> ReviewSendResult:
        settings = await self.settings()
        workspace_name = self.workspace.organization.name
        sent: list[uuid.UUID] = []
        skipped: list[ReviewSkip] = []
        for request_id in dict.fromkeys(body.request_ids):
            outcome = await self._send_one(request_id, settings, workspace_name)
            if isinstance(outcome, ReviewSkip):
                skipped.append(outcome)
            else:
                sent.append(outcome)
        return ReviewSendResult(sent=sent, skipped=skipped)

    async def _mark_skipped(self, row: ReviewRequest, reason: str) -> None:
        row.status = ReviewStatus.SKIPPED.value
        row.skip_reason = reason
        row.updated_at = datetime.now(UTC)
        await self.db.flush()

    async def _send_one(
        self, request_id: uuid.UUID, settings: ReviewSettingsOut, workspace_name: str
    ) -> uuid.UUID | ReviewSkip:
        row = await self._row(request_id)
        if row is None:
            return _skip(request_id, "not_found")
        if row.status not in (ReviewStatus.PENDING.value, ReviewStatus.SKIPPED.value):
            return _skip(row.id, "already_decided")
        link = settings.google_review_url
        if not link:
            return _skip(row.id, "not_set_up")
        contact = (await crm.get_contacts(self.db, self.tenant, [row.contact_id])).get(
            row.contact_id
        )
        deal = await self.db.scalar(
            select(Deal).where(Deal.organization_id == self.org, Deal.id == row.deal_id)
        )
        if contact is None or deal is None:
            await self._mark_skipped(row, "no_channel")
            return _skip(row.id, "no_channel")
        name = _first_name(contact.full_name)
        text_body = render(settings.message, name=name, car=deal.title, link=link)
        key = f"review-{row.id}"
        try:
            async with self.db.begin_nested():
                channel, message_id = await self._deliver(
                    row, settings, contact, deal.title, text_body, workspace_name, key
                )
        except _SkipError as skip:
            await self._mark_skipped(row, skip.reason)
            return _skip(row.id, skip.reason)
        except (ConflictError, ValidationFailedError, NotFoundError) as exc:
            await self._mark_skipped(row, "cannot_send")
            return _skip(row.id, "cannot_send", exc.message)
        except AppError as exc:
            return _skip(row.id, "send_failed", exc.message)
        row.status = ReviewStatus.SENT.value
        row.channel = channel.value
        row.skip_reason = None
        row.message_id = message_id
        row.decided_by_user_id = self.workspace.user.id
        row.decided_at = datetime.now(UTC)
        row.updated_at = row.decided_at
        await self.db.flush()
        await record_workspace_audit(
            self.db,
            self.workspace,
            action="deals.review.sent",
            target_type="deal_review_request",
            target_id=row.id,
            details={"deal_id": str(row.deal_id), "channel": channel.value},
        )
        return row.id

    async def _deliver(
        self,
        row: ReviewRequest,
        settings: ReviewSettingsOut,
        contact: crm.ContactSummary,
        car: str,
        text_body: str,
        workspace_name: str,
        key: str,
    ) -> tuple[ReviewChannel, uuid.UUID]:
        """WhatsApp when possible (free-form inside 24h, else the template), then email."""
        template = (
            await inbox.whatsapp_template(self.db, self.tenant, settings.template_id)
            if settings.template_ready and settings.template_id is not None
            else None
        )
        values = {
            "first_name": _first_name(contact.full_name),
            "vehicle": car,
            "link": settings.google_review_url or "",
        }
        subject = render(
            settings.email_subject,
            name=_first_name(contact.full_name),
            car=car,
            link="",
            workspace=workspace_name,
        )
        try:
            delivered = await inbox.deliver_to_contact(
                self.db,
                self.workspace,
                contact,
                text=text_body,
                email_subject=subject,
                idempotency_key=key,
                template=inbox.TemplateChoice(
                    template.id, template.channel_id, [values[k] for k in settings.params]
                )
                if template is not None
                else None,
            )
        except inbox.NoChannelError as exc:
            raise _SkipError("no_channel") from exc
        return ReviewChannel(delivered.channel), delivered.message_id


class _SkipError(Exception):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason
