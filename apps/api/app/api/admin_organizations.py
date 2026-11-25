"""Platform admin: create, configure, suspend and invite tenants (PR-025).

Every change goes through a SECURITY DEFINER function that checks ``app_is_platform_admin()``
and writes a tenant audit entry in the same transaction (see migration ``0020``). Responses
carry account metadata only, never tenant business data. Invitation links are returned once,
to the admin who created them; only their hash is stored.
"""

import enum
import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, status
from pydantic import AfterValidator, BaseModel, Field
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError

from app.api.admin import ADMIN_ERRORS, OrganizationDetail, _detail
from app.api.ai import MAX_MONTHLY_LIMIT_USD_MICROS
from app.api.workspaces import _check_email
from app.core.auth.deps import DbDep, PlatformAdminDep, WorkspaceAccess, require_permission
from app.core.auth.permissions import Permission
from app.core.config import Settings, get_settings
from app.core.errors import (
    WORKSPACE_ERRORS,
    ConflictError,
    ErrorDetail,
    ErrorResponse,
    NotFoundError,
    ValidationFailedError,
)
from app.core.logging import request_id_var
from app.core.modules.registry import REGISTRY, ModuleKey
from app.core.tenancy.branding import BrandColor, Currency, OrgName, Slug, Timezone
from app.core.tenancy.invitations import INVITATION_TTL, hash_token, new_token
from app.core.tenancy.models import MembershipRole, OrganizationStatus
from app.modules.inbox.channels.base import channel_connected
from app.modules.inbox.models import ChannelKind

SettingsDep = Annotated[Settings, Depends(get_settings)]

router = APIRouter(tags=["admin"])

CREATE_ERRORS = {
    **ADMIN_ERRORS,
    409: {"model": ErrorResponse, "description": "Slug already used"},
}
Email = Annotated[str, AfterValidator(_check_email)]


class OrganizationCreate(BaseModel):
    slug: Slug = Field(examples=["ventur-auto-import"])
    name: OrgName
    timezone: Timezone = "Europe/Malta"
    currency: Currency = "EUR"
    display_name: OrgName | None = None
    brand_color: BrandColor | None = None
    modules: list[ModuleKey] = Field(default_factory=list, max_length=len(REGISTRY))
    owner_email: Email
    ai_monthly_limit_usd_micros: int | None = Field(
        default=None, ge=0, le=MAX_MONTHLY_LIMIT_USD_MICROS
    )
    ai_alert_percent: int = Field(default=80, ge=1, le=100)


class InvitationLink(BaseModel):
    id: uuid.UUID
    email: str
    role: MembershipRole
    expires_at: datetime
    token: str  # Returned once; only its hash is stored.


class OrganizationCreated(BaseModel):
    organization: OrganizationDetail
    invitation: InvitationLink


class OrganizationAdminUpdate(BaseModel):
    """Fields to change; omitted fields stay. ``null`` clears the display name or colour."""

    name: OrgName | None = None
    timezone: Timezone | None = None
    display_name: OrgName | None = None
    brand_color: BrandColor | None = None


class StatusChange(BaseModel):
    status: OrganizationStatus


class InvitationState(enum.StrEnum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REVOKED = "revoked"
    EXPIRED = "expired"


class AdminInvitationOut(BaseModel):
    id: uuid.UUID
    email: str
    role: MembershipRole
    state: InvitationState
    created_at: datetime
    expires_at: datetime
    accepted_at: datetime | None
    revoked_at: datetime | None


class AdminInvitationCreate(BaseModel):
    email: Email
    role: MembershipRole = MembershipRole.OWNER


class ChannelStatus(BaseModel):
    id: uuid.UUID
    kind: ChannelKind
    name: str
    disabled: bool
    connected: bool
    # The customer-facing number of a WhatsApp channel; email addresses stay in the inbox.
    phone_number: str | None


class PhoneLineStatus(BaseModel):
    """A missed-call line (VA-004): the cloud number and the WhatsApp channel it texts from."""

    id: uuid.UUID
    number: str
    provider: str
    whatsapp_channel_name: str
    text_back_enabled: bool


class AIBudgetStatus(BaseModel):
    monthly_limit_usd_micros: int | None
    alert_percent: int | None
    spent_usd_micros: int


class IntegrationStatus(BaseModel):
    channels: list[ChannelStatus]
    email_configured: bool
    whatsapp_configured: bool
    telephony_configured: bool = False
    phone_lines: list[PhoneLineStatus] = []
    ai_budget: AIBudgetStatus | None  # platform admins only


def _ordered(modules: list[ModuleKey]) -> list[ModuleKey]:
    """Requested modules, each after the modules it requires. 422 if one is missing."""
    wanted = set(modules)
    for key in sorted(wanted):
        if missing := sorted(REGISTRY[key].requires - wanted):
            names = ", ".join(m.value for m in missing)
            raise ValidationFailedError(
                f"{key.value} requires {names}; include it too.",
                details=[ErrorDetail(loc=["body", "modules"], msg="Missing", type="requires")],
            )
    ordered: list[ModuleKey] = []
    while len(ordered) < len(wanted):
        for key in sorted(wanted - set(ordered)):
            if REGISTRY[key].requires <= set(ordered):
                ordered.append(key)
    return ordered


def _not_found(exc: DBAPIError) -> bool:
    return getattr(exc.orig, "sqlstate", None) == "P0002"


@router.post(
    "/admin/organizations",
    response_model=OrganizationCreated,
    status_code=status.HTTP_201_CREATED,
    responses=CREATE_ERRORS,
)
async def create_organization(
    body: OrganizationCreate, _admin: PlatformAdminDep, db: DbDep
) -> OrganizationCreated:
    modules = _ordered(body.modules)
    token = new_token()
    expires_at = datetime.now(UTC) + INVITATION_TTL
    rid = request_id_var.get()
    try:
        async with db.begin_nested():
            row = (
                await db.execute(
                    text(
                        "SELECT * FROM app_admin_create_organization(:slug, :name, :tz, "
                        ":currency, :display, :color, :email, :hash, :expires, :rid)"
                    ),
                    {
                        "slug": body.slug,
                        "name": body.name,
                        "tz": body.timezone,
                        "currency": body.currency,
                        "display": body.display_name,
                        "color": body.brand_color,
                        "email": body.owner_email,
                        "hash": hash_token(token),
                        "expires": expires_at,
                        "rid": rid,
                    },
                )
            ).one()
    except IntegrityError as exc:
        raise ConflictError(
            "That slug is already used.",
            details=[ErrorDetail(loc=["body", "slug"], msg="Already used.", type="duplicate")],
        ) from exc
    for key in modules:
        await db.execute(
            text("SELECT app_admin_set_module(:slug, :key, true, :rid)"),
            {"slug": body.slug, "key": key.value, "rid": rid},
        )
    if body.ai_monthly_limit_usd_micros is not None:
        await db.execute(
            text("SELECT app_admin_set_ai_budget(:slug, :limit, CAST(:alert AS smallint), :rid)"),
            {
                "slug": body.slug,
                "limit": body.ai_monthly_limit_usd_micros,
                "alert": body.ai_alert_percent,
                "rid": rid,
            },
        )
    return OrganizationCreated(
        organization=await _detail(db, body.slug),
        invitation=InvitationLink(
            id=row.invitation_id,
            email=body.owner_email,
            role=MembershipRole.OWNER,
            expires_at=expires_at,
            token=token,
        ),
    )


@router.patch(
    "/admin/organizations/{slug}", response_model=OrganizationDetail, responses=ADMIN_ERRORS
)
async def update_organization(
    slug: str, body: OrganizationAdminUpdate, _admin: PlatformAdminDep, db: DbDep
) -> OrganizationDetail:
    sent = body.model_fields_set
    try:
        await db.execute(
            text(
                "SELECT app_admin_update_organization(:slug, :name, :tz, :display, :color, "
                ":set_display, :set_color, :rid)"
            ),
            {
                "slug": slug,
                "name": body.name,
                "tz": body.timezone,
                "display": body.display_name,
                "color": body.brand_color,
                "set_display": "display_name" in sent,
                "set_color": "brand_color" in sent,
                "rid": request_id_var.get(),
            },
        )
    except DBAPIError as exc:
        if _not_found(exc):
            raise NotFoundError("Organisation not found.") from exc
        raise
    return await _detail(db, slug)


@router.put(
    "/admin/organizations/{slug}/status",
    response_model=OrganizationDetail,
    responses=ADMIN_ERRORS,
)
async def set_organization_status(
    slug: str, body: StatusChange, _admin: PlatformAdminDep, db: DbDep
) -> OrganizationDetail:
    try:
        await db.execute(
            text("SELECT app_admin_set_organization_status(:slug, :status, :rid)"),
            {"slug": slug, "status": body.status.value, "rid": request_id_var.get()},
        )
    except DBAPIError as exc:
        if _not_found(exc):
            raise NotFoundError("Organisation not found.") from exc
        raise
    return await _detail(db, slug)


def _state(row: object, now: datetime) -> InvitationState:
    if getattr(row, "accepted_at", None) is not None:
        return InvitationState.ACCEPTED
    if getattr(row, "revoked_at", None) is not None:
        return InvitationState.REVOKED
    expires_at: datetime = getattr(row, "expires_at")  # noqa: B009 - typed access
    return InvitationState.EXPIRED if expires_at <= now else InvitationState.PENDING


async def _invitations(db: DbDep, slug: str) -> list[AdminInvitationOut]:
    await _detail(db, slug)  # 404 for an unknown organisation
    rows = await db.execute(text("SELECT * FROM app_admin_invitations(:slug)"), {"slug": slug})
    now = datetime.now(UTC)
    return [
        AdminInvitationOut(
            id=row.id,
            email=row.email,
            role=MembershipRole(row.role),
            state=_state(row, now),
            created_at=row.created_at,
            expires_at=row.expires_at,
            accepted_at=row.accepted_at,
            revoked_at=row.revoked_at,
        )
        for row in rows
    ]


@router.get(
    "/admin/organizations/{slug}/invitations",
    response_model=list[AdminInvitationOut],
    responses=ADMIN_ERRORS,
)
async def list_invitations(
    slug: str, _admin: PlatformAdminDep, db: DbDep
) -> list[AdminInvitationOut]:
    return await _invitations(db, slug)


@router.post(
    "/admin/organizations/{slug}/invitations",
    response_model=InvitationLink,
    status_code=status.HTTP_201_CREATED,
    responses=ADMIN_ERRORS,
)
async def issue_invitation(
    slug: str, body: AdminInvitationCreate, _admin: PlatformAdminDep, db: DbDep
) -> InvitationLink:
    """A new link for this address. An open invitation to the same address is revoked."""
    await _detail(db, slug)
    token = new_token()
    expires_at = datetime.now(UTC) + INVITATION_TTL
    invitation_id = await db.scalar(
        text("SELECT app_admin_issue_invitation(:slug, :email, :role, :hash, :expires, :rid)"),
        {
            "slug": slug,
            "email": body.email,
            "role": body.role.value,
            "hash": hash_token(token),
            "expires": expires_at,
            "rid": request_id_var.get(),
        },
    )
    return InvitationLink(
        id=invitation_id, email=body.email, role=body.role, expires_at=expires_at, token=token
    )


@router.post(
    "/admin/organizations/{slug}/invitations/{invitation_id}/revoke",
    response_model=list[AdminInvitationOut],
    responses=ADMIN_ERRORS,
)
async def revoke_invitation(
    slug: str, invitation_id: uuid.UUID, _admin: PlatformAdminDep, db: DbDep
) -> list[AdminInvitationOut]:
    await _detail(db, slug)
    try:
        await db.execute(
            text("SELECT app_admin_revoke_invitation(:slug, :id, :rid)"),
            {"slug": slug, "id": invitation_id, "rid": request_id_var.get()},
        )
    except DBAPIError as exc:
        if _not_found(exc):
            raise NotFoundError("Invitation not found.") from exc
        raise
    return await _invitations(db, slug)


def _configured(kind: ChannelKind) -> bool:
    # A connected number stands in for "has a number": only provider settings are checked.
    return channel_connected(kind, phone_number_id="configured")


@router.get(
    "/admin/organizations/{slug}/integrations",
    response_model=IntegrationStatus,
    responses=ADMIN_ERRORS,
)
async def admin_integrations(
    slug: str, _admin: PlatformAdminDep, db: DbDep, settings: SettingsDep
) -> IntegrationStatus:
    await _detail(db, slug)
    rows = await db.execute(text("SELECT * FROM app_admin_channels(:slug)"), {"slug": slug})
    channels = [
        ChannelStatus(
            id=row.id,
            kind=ChannelKind(row.kind),
            name=row.name,
            disabled=row.disabled_at is not None,
            connected=row.disabled_at is None
            and channel_connected(
                ChannelKind(row.kind), phone_number_id="set" if row.has_number else None
            ),
            phone_number=row.display_phone_number,
        )
        for row in rows
    ]
    budget = (
        await db.execute(text("SELECT * FROM app_admin_ai_budget(:slug)"), {"slug": slug})
    ).one()
    lines = await db.execute(text("SELECT * FROM app_admin_phone_lines(:slug)"), {"slug": slug})
    return IntegrationStatus(
        channels=channels,
        email_configured=_configured(ChannelKind.EMAIL),
        whatsapp_configured=_configured(ChannelKind.WHATSAPP),
        telephony_configured=settings.telephony_configured,
        phone_lines=[PhoneLineStatus(**row._mapping) for row in lines],
        ai_budget=AIBudgetStatus(
            monthly_limit_usd_micros=budget.monthly_limit_usd_micros,
            alert_percent=budget.alert_percent,
            spent_usd_micros=budget.spent_usd_micros,
        ),
    )


SettingsWorkspace = Annotated[WorkspaceAccess, require_permission(Permission.WORKSPACE_UPDATE)]


@router.get("/w/{slug}/integrations", response_model=IntegrationStatus, responses=WORKSPACE_ERRORS)
async def workspace_integrations(
    workspace: SettingsWorkspace, db: DbDep, settings: SettingsDep
) -> IntegrationStatus:
    """The workspace's channels and whether each is connected. No credentials or provider ids.

    Tenant policies scope the channels to this workspace, and hide them while the inbox module
    is off.
    """
    del workspace
    # Tenant policies scope the lines too, and hide them while the inbox is off.
    lines = (
        await db.execute(
            text(
                "SELECT l.id, l.provider, l.number, c.name AS whatsapp_channel_name, "
                "l.text_back_enabled FROM inbox_phone_lines l JOIN inbox_channels c "
                "ON c.organization_id = l.organization_id AND c.id = l.whatsapp_channel_id "
                "ORDER BY l.number"
            )
        )
    ).all()
    rows = await db.execute(
        text(
            "SELECT id, kind, name, disabled_at, phone_number_id IS NOT NULL AS has_number, "
            "display_phone_number FROM inbox_channels ORDER BY name"
        )
    )
    channels = [
        ChannelStatus(
            id=row.id,
            kind=ChannelKind(row.kind),
            name=row.name,
            disabled=row.disabled_at is not None,
            connected=row.disabled_at is None
            and channel_connected(
                ChannelKind(row.kind), phone_number_id="set" if row.has_number else None
            ),
            phone_number=row.display_phone_number,
        )
        for row in rows
    ]
    return IntegrationStatus(
        channels=channels,
        email_configured=_configured(ChannelKind.EMAIL),
        whatsapp_configured=_configured(ChannelKind.WHATSAPP),
        telephony_configured=settings.telephony_configured,
        phone_lines=[PhoneLineStatus(**row._mapping) for row in lines],
        ai_budget=None,
    )


class AdminBillingOut(BaseModel):
    plan: str | None
    status: str | None
    current_period_end: datetime | None
    cancel_at_period_end: bool
    has_customer: bool


@router.get(
    "/admin/organizations/{slug}/billing",
    response_model=AdminBillingOut,
    responses=ADMIN_ERRORS,
)
async def admin_billing(slug: str, _admin: PlatformAdminDep, db: DbDep) -> AdminBillingOut:
    """The tenant's plan and subscription status. Read-only: billing changes come from Stripe."""
    await _detail(db, slug)
    row = (await db.execute(text("SELECT * FROM app_admin_billing(:slug)"), {"slug": slug})).one()
    return AdminBillingOut(
        plan=row.plan,
        status=row.status,
        current_period_end=row.current_period_end,
        cancel_at_period_end=row.cancel_at_period_end,
        has_customer=row.has_customer,
    )
