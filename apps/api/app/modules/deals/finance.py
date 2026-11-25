"""Finance pre-qualification (VA-006): settings, the estimate and finance applications.

Onyx never decides finance. It works out the same estimate Ventur publishes, collects the
applicant's details and documents, and lets owners and admins (``finance.manage``) record the
decision. Income and employment details are only returned to them. Linking an application to
a deal marks the deal financed and switches its checklist to the applicant type's documents.
"""

import uuid
from dataclasses import asdict
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit.record import record_workspace_audit
from app.core.auth.deps import WorkspaceAccess
from app.core.auth.permissions import Permission, permissions_for
from app.core.errors import (
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
    ValidationFailedError,
)
from app.core.storage.files import TenantFileService
from app.core.storage.store import ObjectStore
from app.modules.crm import public as crm
from app.modules.deals import schemas
from app.modules.deals.finance_rules import (
    CLOSED,
    DECIDED,
    STANDARD_CHECKLISTS,
    STANDARD_RATES,
    ApplicationStatus,
    EstimateError,
    Rates,
    checklist_for,
    estimate,
)
from app.modules.deals.lifecycle import FINAL_STAGES
from app.modules.deals.models import Deal, FinanceApplication, FinanceSettings

DEFAULT_DISCLAIMER = (
    "This is an estimate only. Final approval, rates and terms depend on checks, documents "
    "and approval."
)
FORM_KINDS = ("kyc", "ccr")
SENSITIVE = ("employer", "net_monthly_income_cents", "existing_commitments_cents", "notes")


async def load_settings(db: AsyncSession, org: uuid.UUID) -> FinanceSettings | None:
    return await db.scalar(select(FinanceSettings).where(FinanceSettings.organization_id == org))


def rates_of(row: FinanceSettings | None) -> Rates:
    if row is None:
        return Rates(**STANDARD_RATES)
    return Rates(
        annual_rate_bp=row.annual_rate_bp,
        onboarding_fee_bp=row.onboarding_fee_bp,
        yearly_fee_bp=row.yearly_fee_bp,
        min_term_months=row.min_term_months,
        max_term_months=row.max_term_months,
    )


def estimate_out(rates: Rates, disclaimer: str, **inputs: Any) -> schemas.EstimateOut:
    try:
        e = estimate(rates, **inputs)
    except EstimateError as exc:
        raise ValidationFailedError(str(exc)) from exc
    return schemas.EstimateOut(
        **asdict(e),
        onboarding_fee_bp=rates.onboarding_fee_bp,
        yearly_fee_bp=rates.yearly_fee_bp,
        disclaimer=disclaimer,
    )


class FinanceService:
    def __init__(self, db: AsyncSession, workspace: WorkspaceAccess) -> None:
        self.db = db
        self.workspace = workspace
        self.tenant = workspace.tenant
        self.org = workspace.tenant.organization_id
        self.can_manage = Permission.FINANCE_MANAGE in permissions_for(workspace.role)

    # --- settings and forms -------------------------------------------------------------------

    async def settings(self) -> schemas.FinanceSettingsOut:
        row = await load_settings(self.db, self.org)
        rates = rates_of(row)
        overrides = row.checklists if row else {}
        return schemas.FinanceSettingsOut(
            annual_rate_bp=rates.annual_rate_bp,
            onboarding_fee_bp=rates.onboarding_fee_bp,
            yearly_fee_bp=rates.yearly_fee_bp,
            min_term_months=rates.min_term_months,
            max_term_months=rates.max_term_months,
            disclaimer=row.disclaimer if row else DEFAULT_DISCLAIMER,
            checklists={**{str(k): v for k, v in STANDARD_CHECKLISTS.items()}, **overrides},
            uses_standard_checklists=not overrides,
            kyc_form=bool(row and row.kyc_form_file_id),
            ccr_form=bool(row and row.ccr_form_file_id),
        )

    async def _row_for_update(self) -> FinanceSettings:
        row = await load_settings(self.db, self.org)
        if row is None:
            row = FinanceSettings(organization_id=self.org, disclaimer=DEFAULT_DISCLAIMER)
            self.db.add(row)
        row.updated_by_user_id = self.workspace.user.id
        return row

    async def update_settings(
        self, body: schemas.FinanceSettingsUpdate
    ) -> schemas.FinanceSettingsOut:
        row = await self._row_for_update()
        sent = {k: v for k, v in body.model_dump(exclude_unset=True).items() if v is not None}
        for key, value in sent.items():
            setattr(row, key, value)
        low = row.min_term_months or 6
        high = row.max_term_months or 120
        if low > high:
            raise ValidationFailedError("The shortest term must not be longer than the longest.")
        await self.db.flush()
        await record_workspace_audit(
            self.db,
            self.workspace,
            action="finance.settings_updated",
            target_type="organization",
            target_id=self.org,
            details={"fields": sorted(sent)},
        )
        return await self.settings()

    async def upload_form(
        self, kind: str, body: schemas.FinanceFormUpload, store: ObjectStore
    ) -> schemas.FinanceSettingsOut:
        from app.modules.deals.service import decode_file

        if kind not in FORM_KINDS:
            raise NotFoundError("Unknown form.")
        data = decode_file(body.content_base64)
        if not data.startswith(b"%PDF-"):
            raise ValidationFailedError("Upload the form as a PDF.")
        row = await self._row_for_update()
        files = TenantFileService(self.db, self.tenant, store)
        stored = await files.upload(
            filename=body.filename,
            content_type="application/pdf",
            data=data,
            created_by_user_id=self.workspace.user.id,
        )
        column = f"{kind}_form_file_id"
        previous = getattr(row, column)
        setattr(row, column, stored.id)
        await self.db.flush()
        if previous is not None:
            await files.delete(previous)
        await record_workspace_audit(
            self.db,
            self.workspace,
            action="finance.form_uploaded",
            target_type="organization",
            target_id=self.org,
            details={"form": kind},
        )
        return await self.settings()

    async def form(self, kind: str, store: ObjectStore) -> tuple[str, bytes]:
        if kind not in FORM_KINDS:
            raise NotFoundError("Unknown form.")
        row = await load_settings(self.db, self.org)
        file_id = getattr(row, f"{kind}_form_file_id") if row else None
        if file_id is None:
            raise NotFoundError("This form has not been uploaded yet.")
        content = await TenantFileService(self.db, self.tenant, store).read(file_id)
        return content.file.filename, content.data

    # --- estimate -----------------------------------------------------------------------------

    async def estimate(self, body: schemas.EstimateRequest) -> schemas.EstimateOut:
        row = await load_settings(self.db, self.org)
        return estimate_out(
            rates_of(row),
            row.disclaimer if row else DEFAULT_DISCLAIMER,
            price_cents=body.price_cents,
            deposit_cents=body.deposit_cents,
            term_months=body.term_months,
            payoff_months=body.payoff_months,
        )

    async def _snapshot(self, app: FinanceApplication) -> None:
        """The estimate for the application's figures, stored with it (or cleared)."""
        if app.price_cents is None or app.term_months is None:
            app.estimate, app.monthly_estimate_cents = {}, None
            return
        row = await load_settings(self.db, self.org)
        out = estimate_out(
            rates_of(row),
            row.disclaimer if row else DEFAULT_DISCLAIMER,
            price_cents=app.price_cents,
            deposit_cents=app.deposit_cents or 0,
            term_months=app.term_months,
        )
        app.estimate = out.model_dump()
        app.monthly_estimate_cents = out.monthly_cents

    # --- applications -------------------------------------------------------------------------

    async def _application(self, app_id: uuid.UUID, *, lock: bool = False) -> FinanceApplication:
        query = select(FinanceApplication).where(
            FinanceApplication.organization_id == self.org, FinanceApplication.id == app_id
        )
        if lock:
            query = query.with_for_update()
        app = await self.db.scalar(query)
        if app is None:
            raise NotFoundError("Finance application not found.")
        return app

    async def _deal(self, deal_id: uuid.UUID) -> Deal:
        deal = await self.db.scalar(
            select(Deal)
            .where(Deal.organization_id == self.org, Deal.id == deal_id)
            .with_for_update()
        )
        if deal is None:
            raise ValidationFailedError("Deal not found.")
        return deal

    async def _sync_deal(self, app: FinanceApplication) -> None:
        if app.deal_id is None:
            return
        from app.modules.deals.service import DealService

        deal = await self._deal(app.deal_id)
        row = await load_settings(self.db, self.org)
        items = checklist_for(
            app.applicant_type, app.marital_status, row.checklists if row else None
        )
        await DealService(self.db, self.workspace).apply_finance_checklist(deal, items)

    async def create(
        self, body: schemas.FinanceApplicationCreate, *, source: str = "staff"
    ) -> schemas.FinanceApplicationDetail:
        sensitive = {k for k in SENSITIVE if getattr(body, k) is not None}
        if sensitive and not self.can_manage:
            raise PermissionDeniedError("Only owners and admins can record income details.")
        contact_id = body.contact_id
        deal: Deal | None = None
        if body.deal_id is not None:
            deal = await self._deal(body.deal_id)
            if deal.stage in FINAL_STAGES:
                raise ConflictError("This deal is closed.")
            if contact_id is not None and contact_id != deal.contact_id:
                raise ValidationFailedError("The deal belongs to another contact.")
            contact_id = deal.contact_id
            taken = await self.db.scalar(
                select(FinanceApplication.id).where(
                    FinanceApplication.organization_id == self.org,
                    FinanceApplication.deal_id == deal.id,
                )
            )
            if taken is not None:
                raise ConflictError("This deal already has a finance application.")
        if contact_id is None:
            raise ValidationFailedError("Choose the customer (a contact).")
        if contact_id not in await crm.get_contacts(self.db, self.tenant, [contact_id]):
            raise ValidationFailedError("Contact not found.")
        app = FinanceApplication(
            organization_id=self.org,
            contact_id=contact_id,
            deal_id=deal.id if deal else None,
            applicant_type=body.applicant_type,
            marital_status=body.marital_status,
            vehicle_label=body.vehicle_label or (deal.title if deal else None),
            price_cents=body.price_cents or (deal.price_cents if deal else None),
            deposit_cents=body.deposit_cents,
            term_months=body.term_months,
            employer=body.employer,
            net_monthly_income_cents=body.net_monthly_income_cents,
            existing_commitments_cents=body.existing_commitments_cents,
            notes=body.notes,
            status=ApplicationStatus.STARTED,
            source=source,
            created_by_user_id=self.workspace.user.id,
        )
        await self._snapshot(app)
        self.db.add(app)
        await self.db.flush()
        if deal is not None:
            deal.financed = True
            await self._sync_deal(app)
        await record_workspace_audit(
            self.db,
            self.workspace,
            action="finance.application_created",
            target_type="finance_application",
            target_id=app.id,
            details={"deal_id": str(app.deal_id) if app.deal_id else None, "source": source},
        )
        await self.db.flush()
        return await self.detail(app.id)

    async def update(
        self, app_id: uuid.UUID, body: schemas.FinanceApplicationUpdate
    ) -> schemas.FinanceApplicationDetail:
        app = await self._application(app_id, lock=True)
        if app.status in CLOSED:
            raise ConflictError("This application is closed.")
        sent = dict(body.model_dump(exclude_unset=True))
        if any(k in SENSITIVE for k in sent) and not self.can_manage:
            raise PermissionDeniedError("Only owners and admins can change income details.")
        for key, value in sent.items():
            if value is not None or key in SENSITIVE:
                setattr(app, key, value)
        await self._snapshot(app)
        if {"applicant_type", "marital_status"} & sent.keys():
            await self._sync_deal(app)
        await self.db.flush()
        return await self.detail(app.id)

    async def change_status(
        self, app_id: uuid.UUID, body: schemas.FinanceStatusChange
    ) -> schemas.FinanceApplicationDetail:
        app = await self._application(app_id, lock=True)
        if (body.status in DECIDED or app.status in CLOSED) and not self.can_manage:
            raise PermissionDeniedError(
                "Only owners and admins record finance decisions or reopen applications."
            )
        if app.status is body.status:
            raise ConflictError("The application is already at this status.")
        before = app.status
        app.status = body.status
        if body.status in DECIDED:
            app.decided_at = datetime.now(UTC)
            app.decided_by_user_id = self.workspace.user.id
            app.decision_note = body.note
        else:
            app.decided_at = None
            app.decided_by_user_id = None
        await self.db.flush()
        await record_workspace_audit(
            self.db,
            self.workspace,
            action="finance.status_changed",
            target_type="finance_application",
            target_id=app.id,
            details={"from": before.value, "to": body.status.value},
        )
        return await self.detail(app.id)

    async def list(self, status: ApplicationStatus | None) -> schemas.FinanceApplicationList:
        query = select(FinanceApplication).where(FinanceApplication.organization_id == self.org)
        if status is not None:
            query = query.where(FinanceApplication.status == status)
        apps = list(
            await self.db.scalars(query.order_by(FinanceApplication.updated_at.desc()).limit(200))
        )
        contacts = await crm.get_contacts(self.db, self.tenant, {a.contact_id for a in apps})
        return schemas.FinanceApplicationList(items=[self._summary(a, contacts) for a in apps])

    def _summary(
        self, app: FinanceApplication, contacts: dict[uuid.UUID, Any]
    ) -> schemas.FinanceApplicationSummary:
        contact = contacts.get(app.contact_id)
        return schemas.FinanceApplicationSummary(
            id=app.id,
            contact=schemas.DealRef(
                id=app.contact_id, label=contact.full_name if contact else "Unknown contact"
            ),
            deal_id=app.deal_id,
            applicant_type=app.applicant_type,
            marital_status=app.marital_status,
            vehicle_label=app.vehicle_label,
            monthly_estimate_cents=app.monthly_estimate_cents,
            status=app.status,
            source=app.source,
            created_at=app.created_at,
            updated_at=app.updated_at,
        )

    async def detail(self, app_id: uuid.UUID) -> schemas.FinanceApplicationDetail:
        app = await self._application(app_id)
        contacts = await crm.get_contacts(self.db, self.tenant, [app.contact_id])
        row = await load_settings(self.db, self.org)
        shown = self.can_manage
        return schemas.FinanceApplicationDetail(
            **self._summary(app, contacts).model_dump(),
            price_cents=app.price_cents,
            deposit_cents=app.deposit_cents,
            term_months=app.term_months,
            estimate=schemas.EstimateOut(**app.estimate) if app.estimate else None,
            decided_at=app.decided_at,
            employer=app.employer if shown else None,
            net_monthly_income_cents=app.net_monthly_income_cents if shown else None,
            existing_commitments_cents=app.existing_commitments_cents if shown else None,
            notes=app.notes if shown else None,
            decision_note=app.decision_note if shown else None,
            restricted=not shown,
            checklist=[
                i.label
                for i in checklist_for(
                    app.applicant_type, app.marital_status, row.checklists if row else None
                )
            ],
        )
