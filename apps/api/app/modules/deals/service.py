"""Deals (VA-007): create, move through stages, record the deposit, collect documents.

Every query runs in the request's tenant-bound transaction (RLS) and filters by the tenant
explicitly. Other modules are reached only through their public interfaces. Document files go
through ``TenantFileService``: a file is readable only with ``deals.documents``, and each
download is audited. Logs and audit entries carry ids and states, never document contents.
"""

import base64
import binascii
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
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
from app.core.modules.access import module_enabled
from app.core.modules.registry import ModuleKey
from app.core.storage.files import TenantFileService
from app.core.storage.models import StoredFile
from app.core.storage.store import ObjectStore
from app.core.tenancy.models import MembershipRole
from app.modules.automotive import public as automotive
from app.modules.crm import public as crm
from app.modules.deals import schemas, uploads
from app.modules.deals.lifecycle import (
    ACTIVE_STAGES,
    FINAL_STAGES,
    MAX_FILE_BYTES,
    REFUSAL_TEXT,
    STANDARD_CHECKLIST,
    ChecklistCondition,
    ChecklistItem,
    DealDocumentState,
    DealStage,
    applies,
    check_move,
    sniff,
)
from app.modules.deals.models import Deal, DealDocument, DealEvent, DealSettings, DealUploadLink
from app.modules.quotations import public as quotations

MAX_LISTED = 200
CUSTOM_KEY_PREFIX = "custom_"


def _now() -> datetime:
    return datetime.now(UTC)


def template_from(row: DealSettings | None) -> list[ChecklistItem]:
    if row is None or not row.checklist:
        return list(STANDARD_CHECKLIST)
    return [
        ChecklistItem(
            key=item["key"],
            label=item["label"],
            required=bool(item.get("required", True)),
            note=item.get("note"),
            when=ChecklistCondition(item.get("when", ChecklistCondition.ALWAYS)),
        )
        for item in row.checklist
    ]


class DealService:
    def __init__(self, db: AsyncSession, workspace: WorkspaceAccess) -> None:
        self.db = db
        self.workspace = workspace
        self.tenant = workspace.tenant
        self.org = workspace.tenant.organization_id

    # --- settings ---------------------------------------------------------------------------

    async def _settings_row(self) -> DealSettings | None:
        return await self.db.scalar(
            select(DealSettings).where(DealSettings.organization_id == self.org)
        )

    async def get_settings(self) -> schemas.DealSettingsOut:
        row = await self._settings_row()
        return schemas.DealSettingsOut(
            checklist=[
                schemas.DealChecklistItemOut(
                    key=i.key, label=i.label, required=i.required, note=i.note, when=i.when
                )
                for i in template_from(row)
            ],
            retention_days=row.retention_days if row else 180,
            customer_reminders=row.customer_reminders if row else False,
            uses_standard_checklist=row is None or not row.checklist,
        )

    async def update_settings(self, body: schemas.DealSettingsUpdate) -> schemas.DealSettingsOut:
        row = await self._settings_row()
        if row is None:
            row = DealSettings(organization_id=self.org)
            self.db.add(row)
        changed: list[str] = []
        if body.checklist is not None:
            keys = [i.key for i in body.checklist]
            if len(set(keys)) != len(keys):
                raise ValidationFailedError("Each checklist item needs its own key.")
            row.checklist = [i.model_dump(mode="json") for i in body.checklist]
            changed.append("checklist")
        if body.retention_days is not None:
            row.retention_days = body.retention_days
            changed.append("retention_days")
        if body.customer_reminders is not None:
            row.customer_reminders = body.customer_reminders
            changed.append("customer_reminders")
        row.updated_by_user_id = self.workspace.user.id
        await self.db.flush()
        await record_workspace_audit(
            self.db,
            self.workspace,
            action="deals.settings.updated",
            target_type="organization",
            target_id=self.org,
            details={"fields": changed},
        )
        return await self.get_settings()

    # --- deals ------------------------------------------------------------------------------

    async def _deal(self, deal_id: uuid.UUID, *, lock: bool = False) -> Deal:
        query = select(Deal).where(Deal.organization_id == self.org, Deal.id == deal_id)
        if lock:
            query = query.with_for_update()
        deal = await self.db.scalar(query)
        if deal is None:
            raise NotFoundError("Deal not found.")
        return deal

    async def _event(self, deal: Deal, kind: str, **values: Any) -> None:
        self.db.add(
            DealEvent(
                organization_id=self.org,
                deal_id=deal.id,
                kind=kind,
                actor_user_id=self.workspace.user.id,
                from_stage=values.pop("from_stage", None),
                to_stage=values.pop("to_stage", None),
                details=values,
            )
        )

    async def _automotive_on(self) -> bool:
        return await module_enabled(self.db, self.workspace, ModuleKey.AUTOMOTIVE)

    async def create(self, body: schemas.DealCreate) -> schemas.DealDetail:
        contact_id = body.contact_id
        if body.quote_id is not None:
            quote = await quotations.quote_state(self.db, self.tenant, body.quote_id)
            if quote is None:
                raise ValidationFailedError("Quote not found.")
            if quote.status != "accepted":
                raise ConflictError("Record the quote as accepted before creating a deal from it.")
            if contact_id is not None and contact_id != quote.contact_id:
                raise ValidationFailedError("The quote belongs to another contact.")
            contact_id = quote.contact_id
        if contact_id is None:
            raise ValidationFailedError("Choose the customer (a contact) for the deal.")
        contacts = await crm.get_contacts(self.db, self.tenant, [contact_id])
        if contact_id not in contacts:
            raise ValidationFailedError("Contact not found.")
        if (
            body.lead_id is not None
            and await crm.get_lead(self.db, self.tenant, body.lead_id) is None
        ):
            raise ValidationFailedError("Lead not found.")

        deal = Deal(
            id=uuid.uuid4(),
            organization_id=self.org,
            title=body.title or contacts[contact_id].full_name,
            contact_id=contact_id,
            lead_id=body.lead_id,
            quote_id=body.quote_id,
            conversation_id=body.conversation_id,
            stage=DealStage.RESERVED,
            financed=body.financed,
            has_trade_in=body.has_trade_in,
            price_cents=body.price_cents,
            assignee_user_id=body.assignee_user_id or self.workspace.user.id,
            created_by_user_id=self.workspace.user.id,
        )
        self.db.add(deal)
        try:
            await self.db.flush()
        except IntegrityError as exc:
            raise ValidationFailedError(
                "A linked conversation or user was not found in this workspace."
            ) from exc

        if body.vehicle_id is not None:
            if not await self._automotive_on():
                raise ValidationFailedError("Vehicles are not enabled for this workspace.")
            try:
                held = await automotive.hold_vehicle(self.db, self.tenant, body.vehicle_id, deal.id)
            except automotive.VehicleUnavailableError as exc:
                raise ConflictError(
                    "This car is not available: it is sold, withdrawn or held by another deal."
                ) from exc
            if held is None:
                raise ValidationFailedError("Vehicle not found.")
            deal.vehicle_id = held.id
            if body.title is None:
                deal.title = f"{contacts[contact_id].full_name} · {held.title}"[:200]
            if deal.price_cents is None:
                deal.price_cents = held.price_cents

        template = template_from(await self._settings_row())
        for position, item in enumerate(template):
            if applies(item, financed=deal.financed, trade_in=deal.has_trade_in, deposit=False):
                self._add_item(deal, item, position)
        await self._event(deal, "created", to_stage=DealStage.RESERVED.value)
        await self.db.flush()
        await record_workspace_audit(
            self.db,
            self.workspace,
            action="deals.created",
            target_type="deal",
            target_id=deal.id,
            details={"vehicle_id": str(deal.vehicle_id) if deal.vehicle_id else None},
        )
        return await self.detail(deal.id)

    def _add_item(self, deal: Deal, item: ChecklistItem, position: int) -> None:
        self.db.add(
            DealDocument(
                organization_id=self.org,
                deal_id=deal.id,
                key=item.key,
                label=item.label,
                note=item.note,
                required=item.required,
                position=position,
                state=DealDocumentState.MISSING,
            )
        )

    async def update(self, deal_id: uuid.UUID, body: schemas.DealUpdate) -> schemas.DealDetail:
        deal = await self._deal(deal_id, lock=True)
        if deal.stage in FINAL_STAGES:
            raise ConflictError("This deal is closed and cannot change.")
        sent = body.model_dump(exclude_unset=True)
        sent = {k: v for k, v in sent.items() if v is not None}
        for key, value in sent.items():
            setattr(deal, key, value)
        if "financed" in sent or "has_trade_in" in sent:
            await self._sync_conditional_items(deal)
        await self.db.flush()
        if sent:
            await self._event(deal, "updated", fields=sorted(sent))
        return await self.detail(deal.id)

    async def _items(self, deal: Deal) -> list[DealDocument]:
        return list(
            await self.db.scalars(
                select(DealDocument)
                .where(DealDocument.organization_id == self.org, DealDocument.deal_id == deal.id)
                .order_by(DealDocument.position, DealDocument.label)
            )
        )

    async def _sync_conditional_items(self, deal: Deal) -> None:
        """Add items that now apply; remove untouched ones that no longer do."""
        template = template_from(await self._settings_row())
        existing = {d.key: d for d in await self._items(deal)}
        for position, item in enumerate(template):
            wanted = applies(
                item,
                financed=deal.financed,
                trade_in=deal.has_trade_in,
                deposit=deal.deposit_cents is not None,
            )
            current = existing.get(item.key)
            if wanted and current is None:
                self._add_item(deal, item, position)
            elif not wanted and current is not None and current.state is DealDocumentState.MISSING:
                await self.db.delete(current)

    async def change_stage(
        self, deal_id: uuid.UUID, body: schemas.DealStageChange
    ) -> schemas.DealDetail:
        deal = await self._deal(deal_id, lock=True)
        items = await self._items(deal)
        unverified = [
            d.label for d in items if d.required and d.state is not DealDocumentState.VERIFIED
        ]
        override = body.override and body.stage is DealStage.SOLD
        if override and self.workspace.role is not MembershipRole.OWNER:
            raise PermissionDeniedError(
                "Only an owner can mark a deal sold with documents missing."
            )
        if override and body.reason is None:
            raise ValidationFailedError("Give a reason for marking it sold anyway.")
        if body.stage is DealStage.CANCELLED and body.reason is None:
            raise ValidationFailedError("Give a reason for cancelling the deal.")
        move = check_move(
            deal.stage,
            body.stage,
            financed=deal.financed,
            has_deposit=deal.deposit_cents is not None,
            unverified_required=unverified,
            override=override,
        )
        if not move.allowed:
            raise ConflictError(REFUSAL_TEXT[move.refusal] if move.refusal else "Not allowed.")

        before, now = deal.stage, _now()
        deal.stage = body.stage
        deal.stage_changed_at = now
        if body.stage is DealStage.SOLD:
            deal.sold_at = now
        if body.stage in FINAL_STAGES:
            deal.closed_at = now
        if body.stage is DealStage.CANCELLED:
            deal.cancel_reason = body.reason
        if deal.vehicle_id is not None:
            if body.stage is DealStage.CANCELLED:
                await automotive.release_vehicle(
                    self.db, self.tenant, deal.vehicle_id, deal.id, sold=False
                )
            elif body.stage is DealStage.COLLECTED:
                await automotive.release_vehicle(
                    self.db, self.tenant, deal.vehicle_id, deal.id, sold=True
                )
            elif body.stage in ACTIVE_STAGES:
                await automotive.set_held_status(
                    self.db,
                    self.tenant,
                    deal.vehicle_id,
                    deal.id,
                    sold=body.stage is DealStage.SOLD,
                )
        details: dict[str, Any] = {}
        if move.overridden:
            details = {"override": True, "reason": body.reason, "unverified": move.missing}
        elif body.stage is DealStage.CANCELLED:
            details = {"reason": body.reason}
        await self._event(
            deal, "stage_changed", from_stage=before.value, to_stage=body.stage.value, **details
        )
        await self.db.flush()
        await record_workspace_audit(
            self.db,
            self.workspace,
            action="deals.stage_changed",
            target_type="deal",
            target_id=deal.id,
            details={"from": before.value, "to": body.stage.value, "override": move.overridden},
        )
        return await self.detail(deal.id)

    async def record_deposit(
        self, deal_id: uuid.UUID, body: schemas.DealDepositRecord
    ) -> schemas.DealDetail:
        deal = await self._deal(deal_id, lock=True)
        if deal.stage in FINAL_STAGES or deal.stage is DealStage.SOLD:
            raise ConflictError("The deposit can only be recorded before the deal is sold.")
        deal.deposit_cents = body.amount_cents
        deal.deposit_received_on = body.received_on
        deal.deposit_method = body.method
        await self._sync_conditional_items(deal)
        await self._event(
            deal, "deposit_recorded", amount_cents=body.amount_cents, method=body.method.value
        )
        if deal.stage is DealStage.RESERVED:
            deal.stage = DealStage.DEPOSIT_RECEIVED
            deal.stage_changed_at = _now()
            await self._event(
                deal,
                "stage_changed",
                from_stage=DealStage.RESERVED.value,
                to_stage=DealStage.DEPOSIT_RECEIVED.value,
            )
        await self.db.flush()
        await record_workspace_audit(
            self.db,
            self.workspace,
            action="deals.deposit_recorded",
            target_type="deal",
            target_id=deal.id,
            details={"amount_cents": body.amount_cents, "method": body.method.value},
        )
        return await self.detail(deal.id)

    # --- documents --------------------------------------------------------------------------

    async def _item(self, deal: Deal, document_id: uuid.UUID) -> DealDocument:
        item = await self.db.scalar(
            select(DealDocument).where(
                DealDocument.organization_id == self.org,
                DealDocument.deal_id == deal.id,
                DealDocument.id == document_id,
            )
        )
        if item is None:
            raise NotFoundError("Document not found.")
        return item

    async def add_item(
        self, deal_id: uuid.UUID, body: schemas.DealDocumentAdd
    ) -> schemas.DealDetail:
        deal = await self._deal(deal_id, lock=True)
        if deal.stage in FINAL_STAGES:
            raise ConflictError("This deal is closed and cannot change.")
        items = await self._items(deal)
        key = f"{CUSTOM_KEY_PREFIX}{len(items) + 1}_{uuid.uuid4().hex[:6]}"
        self._add_item(
            deal,
            ChecklistItem(key=key, label=body.label, required=body.required, note=body.note),
            max((d.position for d in items), default=0) + 1,
        )
        await self._event(deal, "document_added", label=body.label)
        await self.db.flush()
        return await self.detail(deal.id)

    async def upload(
        self,
        deal_id: uuid.UUID,
        document_id: uuid.UUID,
        body: schemas.DealDocumentUpload,
        store: ObjectStore,
    ) -> schemas.DealDetail:
        deal = await self._deal(deal_id, lock=True)
        if deal.stage in FINAL_STAGES:
            raise ConflictError("This deal is closed and cannot change.")
        item = await self._item(deal, document_id)
        if item.state is DealDocumentState.VERIFIED:
            raise ConflictError("This document is already verified.")
        data = decode_file(body.content_base64)
        content_type = sniff(data)
        if content_type is None:
            raise ValidationFailedError("Upload a PDF, JPEG, PNG or HEIC file.")
        files = TenantFileService(self.db, self.tenant, store)
        previous = item.file_id
        stored = await files.upload(
            filename=body.filename,
            content_type=content_type,
            data=data,
            created_by_user_id=self.workspace.user.id,
        )
        item.file_id = stored.id
        item.state = DealDocumentState.RECEIVED
        item.rejection_reason = None
        item.received_at = _now()
        item.received_from = "staff"
        item.file_deleted_at = None
        await self.db.flush()
        if previous is not None:
            await files.delete(previous)
        await self._event(deal, "document_received", document=item.label, source="staff")
        await self.db.flush()
        return await self.detail(deal.id)

    async def download(
        self, deal_id: uuid.UUID, document_id: uuid.UUID, store: ObjectStore
    ) -> tuple[StoredFile, bytes]:
        deal = await self._deal(deal_id)
        item = await self._item(deal, document_id)
        if item.file_id is None:
            raise NotFoundError("No file for this document.")
        content = await TenantFileService(self.db, self.tenant, store).read(item.file_id)
        await record_workspace_audit(
            self.db,
            self.workspace,
            action="deals.document_opened",
            target_type="deal_document",
            target_id=item.id,
            details={"deal_id": str(deal.id), "key": item.key},
        )
        return content.file, content.data

    async def verify(self, deal_id: uuid.UUID, document_id: uuid.UUID) -> schemas.DealDetail:
        deal = await self._deal(deal_id, lock=True)
        item = await self._item(deal, document_id)
        if item.state is not DealDocumentState.RECEIVED:
            raise ConflictError("Only a received document can be verified.")
        item.state = DealDocumentState.VERIFIED
        item.verified_by_user_id = self.workspace.user.id
        item.verified_at = _now()
        await self._event(deal, "document_verified", document=item.label)
        await self.db.flush()
        await record_workspace_audit(
            self.db,
            self.workspace,
            action="deals.document_verified",
            target_type="deal_document",
            target_id=item.id,
            details={"deal_id": str(deal.id), "key": item.key},
        )
        return await self.detail(deal.id)

    async def reject(
        self, deal_id: uuid.UUID, document_id: uuid.UUID, body: schemas.DealDocumentReject
    ) -> schemas.DealDetail:
        deal = await self._deal(deal_id, lock=True)
        item = await self._item(deal, document_id)
        if item.state not in (DealDocumentState.RECEIVED, DealDocumentState.VERIFIED):
            raise ConflictError("Only a received or verified document can be rejected.")
        item.state = DealDocumentState.REJECTED
        item.rejection_reason = body.reason
        item.verified_by_user_id = None
        item.verified_at = None
        await self._event(deal, "document_rejected", document=item.label, reason=body.reason)
        await self.db.flush()
        await record_workspace_audit(
            self.db,
            self.workspace,
            action="deals.document_rejected",
            target_type="deal_document",
            target_id=item.id,
            details={"deal_id": str(deal.id), "key": item.key},
        )
        return await self.detail(deal.id)

    # --- customer upload links (part 2) -----------------------------------------------------

    async def create_upload_link(self, deal_id: uuid.UUID) -> schemas.UploadLinkCreated:
        """A new link for the customer; any earlier link of the deal stops working."""
        deal = await self._deal(deal_id, lock=True)
        if deal.stage in FINAL_STAGES or deal.stage is DealStage.SOLD:
            raise ConflictError("Documents can only be requested before the deal is sold.")
        await uploads.revoke_links(self.db, self.org, deal.id)
        token, token_hash = uploads.new_token()
        link = DealUploadLink(
            organization_id=self.org,
            deal_id=deal.id,
            token_hash=token_hash,
            expires_at=_now() + uploads.LINK_LIFETIME,
            created_by_user_id=self.workspace.user.id,
        )
        self.db.add(link)
        await self._event(deal, "upload_link_created")
        await self.db.flush()
        await record_workspace_audit(
            self.db,
            self.workspace,
            action="deals.upload_link_created",
            target_type="deal",
            target_id=deal.id,
            details={"link_id": str(link.id)},
        )
        return schemas.UploadLinkCreated(token=token, expires_at=link.expires_at)

    async def revoke_upload_links(self, deal_id: uuid.UUID) -> schemas.DealDetail:
        deal = await self._deal(deal_id, lock=True)
        if await uploads.revoke_links(self.db, self.org, deal.id):
            await self._event(deal, "upload_link_revoked")
            await record_workspace_audit(
                self.db,
                self.workspace,
                action="deals.upload_link_revoked",
                target_type="deal",
                target_id=deal.id,
            )
        await self.db.flush()
        return await self.detail(deal.id)

    # --- reading ----------------------------------------------------------------------------

    async def list_deals(
        self, *, stage: DealStage | None, q: str | None, include_closed: bool
    ) -> schemas.DealList:
        conditions: list[Any] = [Deal.organization_id == self.org]
        if stage is not None:
            conditions.append(Deal.stage == stage)
        elif not include_closed:
            conditions.append(Deal.stage.not_in(list(FINAL_STAGES)))
        if q:
            pattern = f"%{q.strip()}%"
            conditions.append(or_(Deal.title.ilike(pattern)))
        total = await self.db.scalar(select(func.count(Deal.id)).where(*conditions)) or 0
        deals = list(
            await self.db.scalars(
                select(Deal).where(*conditions).order_by(Deal.updated_at.desc()).limit(MAX_LISTED)
            )
        )
        return schemas.DealList(items=await self._summaries(deals), total=total)

    async def _summaries(self, deals: list[Deal]) -> list[schemas.DealSummary]:
        if not deals:
            return []
        contacts = await crm.get_contacts(self.db, self.tenant, {d.contact_id for d in deals})
        vehicles = (
            await automotive.vehicle_titles(
                self.db, self.tenant, {d.vehicle_id for d in deals if d.vehicle_id}
            )
            if any(d.vehicle_id for d in deals) and await self._automotive_on()
            else {}
        )
        counts: dict[uuid.UUID, dict[str, int]] = {}
        rows = await self.db.execute(
            select(DealDocument.deal_id, DealDocument.state, DealDocument.required).where(
                DealDocument.organization_id == self.org,
                DealDocument.deal_id.in_([d.id for d in deals]),
            )
        )
        for row in rows:
            c = counts.setdefault(row.deal_id, {"total": 0, "verified": 0, "missing": 0})
            if not row.required:
                continue
            c["total"] += 1
            if row.state is DealDocumentState.VERIFIED:
                c["verified"] += 1
            elif row.state in (DealDocumentState.MISSING, DealDocumentState.REJECTED):
                c["missing"] += 1
        out = []
        for d in deals:
            c = counts.get(d.id, {"total": 0, "verified": 0, "missing": 0})
            contact = contacts.get(d.contact_id)
            out.append(
                schemas.DealSummary(
                    id=d.id,
                    title=d.title,
                    stage=d.stage,
                    contact=schemas.DealRef(
                        id=d.contact_id, label=contact.full_name if contact else "Unknown contact"
                    ),
                    vehicle=(
                        schemas.DealRef(
                            id=d.vehicle_id, label=vehicles.get(d.vehicle_id, "Vehicle")
                        )
                        if d.vehicle_id
                        else None
                    ),
                    financed=d.financed,
                    price_cents=d.price_cents,
                    documents_total=c["total"],
                    documents_verified=c["verified"],
                    documents_missing=c["missing"],
                    assignee_user_id=d.assignee_user_id,
                    stage_changed_at=d.stage_changed_at,
                    updated_at=d.updated_at,
                )
            )
        return out

    async def detail(self, deal_id: uuid.UUID) -> schemas.DealDetail:
        deal = await self._deal(deal_id)
        (summary,) = await self._summaries([deal])
        can_open = Permission.DEALS_DOCUMENTS in permissions_for(self.workspace.role)
        items = await self._items(deal)
        file_ids = [d.file_id for d in items if d.file_id]
        files = (
            {
                f.id: f
                for f in await self.db.scalars(
                    select(StoredFile).where(
                        StoredFile.organization_id == self.org, StoredFile.id.in_(file_ids)
                    )
                )
            }
            if file_ids and can_open
            else {}
        )
        events = await self.db.scalars(
            select(DealEvent)
            .where(DealEvent.organization_id == self.org, DealEvent.deal_id == deal.id)
            .order_by(DealEvent.occurred_at.desc(), DealEvent.id)
            .limit(100)
        )
        quote_label = (
            (await quotations.quote_numbers(self.db, self.tenant, [deal.quote_id])).get(
                deal.quote_id, "Quote"
            )
            if deal.quote_id
            else None
        )
        link = await uploads.active_link(self.db, self.org, deal.id)
        return schemas.DealDetail(
            **summary.model_dump(),
            upload_link=schemas.UploadLinkOut(
                expires_at=link.expires_at,
                upload_count=link.upload_count,
                max_uploads=link.max_uploads,
                created_at=link.created_at,
            )
            if link is not None and link.upload_count < link.max_uploads
            else None,
            lead_id=deal.lead_id,
            quote=schemas.DealRef(id=deal.quote_id, label=quote_label or "Quote")
            if deal.quote_id
            else None,
            conversation_id=deal.conversation_id,
            has_trade_in=deal.has_trade_in,
            deposit_cents=deal.deposit_cents,
            deposit_received_on=deal.deposit_received_on,
            deposit_method=deal.deposit_method,
            cancel_reason=deal.cancel_reason,
            sold_at=deal.sold_at,
            closed_at=deal.closed_at,
            created_at=deal.created_at,
            documents=[
                schemas.DealDocumentOut(
                    id=d.id,
                    key=d.key,
                    label=d.label,
                    note=d.note,
                    required=d.required,
                    state=d.state,
                    rejection_reason=d.rejection_reason,
                    has_file=d.file_id is not None,
                    filename=files[d.file_id].filename if d.file_id in files else None,
                    content_type=files[d.file_id].content_type if d.file_id in files else None,
                    size_bytes=files[d.file_id].size_bytes if d.file_id in files else None,
                    received_at=d.received_at,
                    received_from=d.received_from,
                    verified_at=d.verified_at,
                    file_deleted_at=d.file_deleted_at,
                )
                for d in items
            ],
            events=[
                schemas.DealEventOut(
                    id=e.id,
                    kind=e.kind,
                    from_stage=e.from_stage,
                    to_stage=e.to_stage,
                    details=e.details,
                    actor_user_id=e.actor_user_id,
                    occurred_at=e.occurred_at,
                )
                for e in events
            ],
        )


def decode_file(content_base64: str) -> bytes:
    try:
        data = base64.b64decode(content_base64, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValidationFailedError("The file could not be read. Try uploading it again.") from exc
    if not data:
        raise ValidationFailedError("The file is empty.")
    if len(data) > MAX_FILE_BYTES:
        raise ValidationFailedError("Files can be at most 10 MB.")
    return data
