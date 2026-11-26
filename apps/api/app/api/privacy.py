"""Data protection tools: export and erase one person's data (owners only).

- ``GET /w/{slug}/privacy/contacts/{id}/export``: everything Onyx holds about the contact, as
  JSON. Each export is audited (ids only).
- ``POST /w/{slug}/privacy/contacts/{id}/erase``: redacts the person everywhere through
  ``app_erase_contact`` (one transaction, SECURITY DEFINER, owners only), then deletes their
  deal document files. Amounts, dates, numbers and opt-outs stay. Cannot be undone.

Every query runs in the bound tenant (RLS), so another workspace's contact is "not found".
"""

import logging
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Annotated, Any

from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import DBAPIError

from app.core.audit.record import record_workspace_audit
from app.core.auth.deps import DbDep, WorkspaceAccess, require_permission
from app.core.auth.permissions import Permission
from app.core.errors import WORKSPACE_ERRORS, ConflictError, NotFoundError, ValidationFailedError
from app.core.logging import request_id_var
from app.core.privacy.models import PrivacySettings
from app.core.storage.files import StoredFileNotFoundError, TenantFileService
from app.core.storage.store import ObjectStore

logger = logging.getLogger("onyx.privacy")
router = APIRouter(tags=["privacy"])

Owner = Annotated[WorkspaceAccess, require_permission(Permission.PRIVACY_MANAGE)]

CONVS = (
    "(SELECT c2.id FROM inbox_conversations c2 WHERE c2.organization_id = :org "
    "AND (c2.contact_id = :c OR EXISTS (SELECT 1 FROM inbox_participants p "
    "WHERE p.organization_id = :org AND p.conversation_id = c2.id AND p.contact_id = :c)))"
)

# (section name, SQL) for the export. Each query is scoped by :org and the contact.
EXPORT_QUERIES: list[tuple[str, str]] = [
    (
        "contact",
        "SELECT id, full_name, email, phone, notes, customer_id, created_at, updated_at, "
        "archived_at, erased_at FROM crm_contacts WHERE organization_id = :org AND id = :c",
    ),
    (
        "customer",
        "SELECT cu.id, cu.name, cu.vat_number, cu.notes, cu.created_at FROM crm_customers cu "
        "JOIN crm_contacts c ON c.organization_id = cu.organization_id AND c.customer_id = cu.id "
        "WHERE cu.organization_id = :org AND c.id = :c",
    ),
    (
        "leads",
        "SELECT id, title, status, notes, lost_reason, created_at, updated_at FROM crm_leads "
        "WHERE organization_id = :org AND contact_id = :c ORDER BY created_at",
    ),
    (
        "activities",
        "SELECT a.id, a.kind, a.subject_type, a.body, a.details, a.occurred_at "
        "FROM crm_activities a WHERE a.organization_id = :org AND (a.subject_id = :c OR "
        "a.subject_id IN (SELECT id FROM crm_leads WHERE organization_id = :org "
        "AND contact_id = :c)) ORDER BY a.occurred_at",
    ),
    (
        "conversations",
        "SELECT c.id, c.subject, c.status, ch.kind AS channel, c.created_at, c.last_message_at "  # noqa: S608 - CONVS is a constant
        "FROM inbox_conversations c JOIN inbox_channels ch "
        "ON ch.organization_id = c.organization_id AND ch.id = c.channel_id "
        f"WHERE c.organization_id = :org AND c.id IN {CONVS} "
        "ORDER BY c.created_at",
    ),
    (
        "messages",
        "SELECT m.conversation_id, m.direction, m.author_kind, m.body, m.occurred_at "  # noqa: S608 - CONVS is a constant
        "FROM inbox_messages m WHERE m.organization_id = :org "
        f"AND m.conversation_id IN {CONVS} ORDER BY m.occurred_at",
    ),
    (
        "quotes",
        "SELECT q.id, q.number, q.title, q.status, q.current_version, q.created_at, "
        "v.gross_minor AS total_cents, v.notes FROM quotations_quotes q "
        "LEFT JOIN quotations_versions v "
        "ON v.organization_id = q.organization_id AND v.quote_id = q.id "
        "AND v.version = q.current_version "
        "WHERE q.organization_id = :org AND q.contact_id = :c ORDER BY q.created_at",
    ),
    (
        "deals",
        "SELECT id, title, stage, financed, has_trade_in, price_cents, deposit_cents, "
        "deposit_received_on, deposit_method, created_at, sold_at, closed_at FROM deals "
        "WHERE organization_id = :org AND contact_id = :c ORDER BY created_at",
    ),
    (
        "finance_applications",
        "SELECT id, deal_id, applicant_type, marital_status, vehicle_label, price_cents, "
        "deposit_cents, term_months, monthly_estimate_cents, employer, "
        "net_monthly_income_cents, existing_commitments_cents, notes, status, decision_note, "
        "decided_at, created_at FROM finance_applications "
        "WHERE organization_id = :org AND contact_id = :c ORDER BY created_at",
    ),
    (
        "marketing_consents",
        "SELECT purpose, method, note, granted_at, withdrawn_at, withdrawn_via "
        "FROM crm_marketing_consents WHERE organization_id = :org AND contact_id = :c "
        "ORDER BY granted_at",
    ),
    (
        "wanted_cars",
        "SELECT make, model, price_max_cents, year_min, mileage_max_km, fuel, active, source, "
        "created_at FROM automotive_wanted WHERE organization_id = :org AND contact_id = :c "
        "ORDER BY created_at",
    ),
    (
        "car_alerts",
        "SELECT v.title AS vehicle, m.status, m.created_at, m.decided_at "
        "FROM automotive_matches m JOIN automotive_vehicles v "
        "ON v.organization_id = m.organization_id AND v.id = m.vehicle_id "
        "WHERE m.organization_id = :org AND m.contact_id = :c ORDER BY m.created_at",
    ),
    (
        "cars_asked_about",
        "SELECT v.title AS vehicle, i.source, i.last_at FROM automotive_interests i "
        "JOIN automotive_vehicles v ON v.organization_id = i.organization_id "
        "AND v.id = i.vehicle_id WHERE i.organization_id = :org AND i.contact_id = :c "
        "ORDER BY i.last_at",
    ),
    (
        "sold_car_follow_ups",
        "SELECT v.title AS sold_vehicle, f.status, f.created_at, f.decided_at "
        "FROM automotive_followups f JOIN automotive_vehicles v "
        "ON v.organization_id = f.organization_id AND v.id = f.sold_vehicle_id "
        "WHERE f.organization_id = :org AND f.contact_id = :c ORDER BY f.created_at",
    ),
    (
        "review_requests",
        "SELECT r.deal_id, r.status, r.channel, r.created_at, r.decided_at "
        "FROM deal_review_requests r WHERE r.organization_id = :org AND r.contact_id = :c "
        "ORDER BY r.created_at",
    ),
    (
        "deal_documents",
        "SELECT d.deal_id, d.label, d.state, d.received_at, d.received_from, d.verified_at, "
        "d.file_deleted_at, f.filename, f.content_type, f.size_bytes FROM deal_documents d "
        "LEFT JOIN stored_files f ON f.organization_id = d.organization_id AND f.id = d.file_id "
        "WHERE d.organization_id = :org AND d.deal_id IN (SELECT id FROM deals "
        "WHERE organization_id = :org AND contact_id = :c) ORDER BY d.deal_id, d.position",
    ),
]


def _plain(value: Any) -> Any:
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    return value


async def _module_on(db: DbDep, org: uuid.UUID, key: str) -> bool:
    return bool(
        await db.scalar(text("SELECT app_module_enabled(:org, :k)"), {"org": org, "k": key})
    )


@router.get(
    "/w/{slug}/privacy/contacts/{contact_id}/export",
    responses={**WORKSPACE_ERRORS, 200: {"content": {"application/json": {}}}},
)
async def export_contact(contact_id: uuid.UUID, workspace: Owner, db: DbDep) -> JSONResponse:
    org = workspace.tenant.organization_id
    params = {"org": org, "c": contact_id}
    exists = await db.scalar(
        text("SELECT 1 FROM crm_contacts WHERE organization_id = :org AND id = :c"), params
    )
    if exists is None:
        raise NotFoundError("Contact not found.")
    sections: dict[str, Any] = {}
    skip = {
        "conversations": "inbox",
        "messages": "inbox",
        "quotes": "quotations",
        "deals": "deals",
        "deal_documents": "deals",
        "finance_applications": "deals",
        "review_requests": "deals",
        "marketing_consents": "crm",
        "wanted_cars": "automotive",
        "car_alerts": "automotive",
        "cars_asked_about": "automotive",
        "sold_car_follow_ups": "automotive",
    }
    for name, sql in EXPORT_QUERIES:
        module = skip.get(name)
        if module is not None and not await _module_on(db, org, module):
            sections[name] = []
            continue
        rows = (await db.execute(text(sql), params)).mappings().all()
        items = [{k: _plain(v) for k, v in row.items()} for row in rows]
        sections[name] = items[0] if name in ("contact", "customer") and items else items
    if not sections.get("customer"):
        sections["customer"] = None
    await record_workspace_audit(
        db,
        workspace,
        action="privacy.contact_exported",
        target_type="contact",
        target_id=contact_id,
    )
    body = {
        "exported_at": datetime.now(UTC).isoformat(),
        "workspace": workspace.organization.slug,
        "note": "Document files are not included; open them from each deal.",
        **sections,
    }
    return JSONResponse(
        body,
        headers={
            "Content-Disposition": f'attachment; filename="contact-{contact_id}.json"',
            "Cache-Control": "private, no-store",
        },
    )


class EraseRequest(BaseModel):
    confirm_name: Annotated[str, Field(min_length=1, max_length=200)] = Field(
        description="The contact's current full name, typed to confirm"
    )


class EraseResult(BaseModel):
    erased_at: datetime
    files_deleted: int


@router.post(
    "/w/{slug}/privacy/contacts/{contact_id}/erase",
    response_model=EraseResult,
    status_code=status.HTTP_200_OK,
    responses=WORKSPACE_ERRORS,
)
async def erase_contact(
    contact_id: uuid.UUID, body: EraseRequest, workspace: Owner, db: DbDep, request: Request
) -> EraseResult:
    org = workspace.tenant.organization_id
    row = (
        await db.execute(
            text(
                "SELECT full_name, erased_at FROM crm_contacts "
                "WHERE organization_id = :org AND id = :c"
            ),
            {"org": org, "c": contact_id},
        )
    ).first()
    if row is None:
        raise NotFoundError("Contact not found.")
    if row.erased_at is not None:
        raise ConflictError("This contact has already been erased.")
    if body.confirm_name.strip().casefold() != row.full_name.strip().casefold():
        raise ValidationFailedError("Type the contact's full name exactly to confirm.")
    try:
        async with db.begin_nested():
            files = list(
                (
                    await db.execute(
                        text("SELECT removed_file FROM app_erase_contact(:c, :rid)"),
                        {"c": contact_id, "rid": request_id_var.get()},
                    )
                )
                .scalars()
                .all()
            )
    except DBAPIError as exc:
        if getattr(getattr(exc.orig, "diag", None), "sqlstate", None) == "P0002":
            raise NotFoundError("Contact not found.") from exc
        raise
    # Finance applications (VA-006): keep the figures, drop the personal details.
    if await _module_on(db, org, "deals"):
        await db.execute(
            text(
                "UPDATE finance_applications SET employer = NULL, notes = NULL, "
                "decision_note = NULL, vehicle_label = NULL, net_monthly_income_cents = NULL, "
                "existing_commitments_cents = NULL, updated_at = now() "
                "WHERE organization_id = :org AND contact_id = :c"
            ),
            {"org": org, "c": contact_id},
        )
        # Review requests (VA-009): never send one to an erased contact.
        await db.execute(
            text(
                "UPDATE deal_review_requests SET status = 'skipped', skip_reason = 'erased', "
                "updated_at = now() WHERE organization_id = :org AND contact_id = :c "
                "AND status IN ('pending', 'skipped')"
            ),
            {"org": org, "c": contact_id},
        )
    # Consent records and wanted criteria (VA-005) go entirely.
    params = {"org": org, "c": contact_id}
    if await _module_on(db, org, "automotive"):
        for table in ("automotive_matches", "automotive_followups", "automotive_interests"):
            await db.execute(
                text(f"DELETE FROM {table} WHERE organization_id = :org AND contact_id = :c"),  # noqa: S608 - fixed names
                params,
            )
        await db.execute(
            text("DELETE FROM automotive_wanted WHERE organization_id = :org AND contact_id = :c"),
            params,
        )
    if await _module_on(db, org, "crm"):
        await db.execute(
            text(
                "DELETE FROM crm_marketing_consents WHERE organization_id = :org "
                "AND contact_id = :c"
            ),
            params,
        )
    store: ObjectStore | None = getattr(request.app.state, "object_store", None)
    deleted = 0
    for file_id in files:
        if store is not None:
            try:
                await TenantFileService(db, workspace.tenant, store).delete(file_id)
                deleted += 1
            except StoredFileNotFoundError:
                continue
        else:
            await db.execute(
                text("DELETE FROM stored_files WHERE organization_id = :org AND id = :f"),
                {"org": org, "f": file_id},
            )
            logger.warning("erase: no object store; file rows removed only")
            deleted += 1
    return EraseResult(erased_at=datetime.now(UTC), files_deleted=deleted)


# --- retention settings (part 2) ------------------------------------------------------------

RETENTION_CHOICES = (6, 12, 24, 36, 60, 120)


class PrivacySettingsOut(BaseModel):
    conversation_retention_months: int | None
    choices: list[int]


class PrivacySettingsUpdate(BaseModel):
    conversation_retention_months: int | None = Field(
        default=None, description="6, 12, 24, 36, 60 or 120; null keeps conversations"
    )


@router.get(
    "/w/{slug}/privacy/settings", response_model=PrivacySettingsOut, responses=WORKSPACE_ERRORS
)
async def read_privacy_settings(workspace: Owner, db: DbDep) -> PrivacySettingsOut:
    months = await db.scalar(
        select(PrivacySettings.conversation_retention_months).where(
            PrivacySettings.organization_id == workspace.tenant.organization_id
        )
    )
    return PrivacySettingsOut(conversation_retention_months=months, choices=list(RETENTION_CHOICES))


@router.put(
    "/w/{slug}/privacy/settings", response_model=PrivacySettingsOut, responses=WORKSPACE_ERRORS
)
async def update_privacy_settings(
    body: PrivacySettingsUpdate, workspace: Owner, db: DbDep
) -> PrivacySettingsOut:
    months = body.conversation_retention_months
    if months is not None and months not in RETENTION_CHOICES:
        raise ValidationFailedError("Choose 6, 12, 24, 36, 60 or 120 months, or keep everything.")
    org = workspace.tenant.organization_id
    await db.execute(
        insert(PrivacySettings)
        .values(
            organization_id=org,
            conversation_retention_months=months,
            updated_by_user_id=workspace.user.id,
        )
        .on_conflict_do_update(
            index_elements=[PrivacySettings.organization_id],
            set_={
                "conversation_retention_months": months,
                "updated_by_user_id": workspace.user.id,
                "updated_at": func.now(),
            },
        )
    )
    await record_workspace_audit(
        db,
        workspace,
        action="privacy.settings_updated",
        target_type="organization",
        target_id=org,
        details={"conversation_retention_months": months},
    )
    return PrivacySettingsOut(conversation_retention_months=months, choices=list(RETENTION_CHOICES))
