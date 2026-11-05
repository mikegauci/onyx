"""CRM domain service: the only code that changes CRM rows.

Every method runs inside the request transaction, bound to the caller's workspace. The tenant
comes from ``WorkspaceAccess`` (never from input); repositories add an explicit
``organization_id`` filter on top of row-level security. Each change writes its activity entry
and its audit entry in the same transaction, so a rejected change leaves neither.
"""

import uuid
from collections.abc import Iterable
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Select, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit.record import record_workspace_audit
from app.core.auth.deps import WorkspaceAccess
from app.core.db.repository import TenantRepository
from app.core.errors import ConflictError, ErrorDetail, NotFoundError, ValidationFailedError
from app.core.logging import request_id_var
from app.core.tenancy.models import Membership, User
from app.modules.crm import schemas
from app.modules.crm.importer import ImportFileError, ImportRow, parse_contacts_csv
from app.modules.crm.lifecycle import allowed_transitions, can_transition
from app.modules.crm.models import (
    Activity,
    ActivityKind,
    Contact,
    Customer,
    CustomerKind,
    Lead,
    LeadSource,
    LeadStatus,
    SubjectType,
)
from app.modules.crm.pagination import encode_cursor, paginate

UNIQUE_IDENTITY_INDEXES = {
    "uq_crm_contacts_organization_id_email": "email",
    "uq_crm_contacts_organization_id_phone": "phone",
}


class CustomerRepository(TenantRepository[Customer]):
    model = Customer


class ContactRepository(TenantRepository[Contact]):
    model = Contact


class LeadRepository(TenantRepository[Lead]):
    model = Lead


class DuplicateContactError(ConflictError):
    default_message = "A contact with this email or phone number already exists."


def _like(term: str) -> str:
    escaped = term.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _changes(model: Any, values: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in values.items() if getattr(model, k) != v}


def _page[T](rows: list[T], limit: int, key: Any) -> tuple[list[T], str | None]:
    page = rows[:limit]
    if len(rows) <= limit:
        return page, None
    when, item_id = key(page[-1])
    return page, encode_cursor(when, item_id)


class CrmService:
    def __init__(self, db: AsyncSession, workspace: WorkspaceAccess) -> None:
        self.db = db
        self.workspace = workspace
        self.org = workspace.tenant.organization_id
        self.customers = CustomerRepository(db, workspace.tenant)
        self.contacts = ContactRepository(db, workspace.tenant)
        self.leads = LeadRepository(db, workspace.tenant)

    # --- shared ----------------------------------------------------------------------------

    def _activity(
        self,
        subject_type: SubjectType,
        subject_id: uuid.UUID,
        kind: ActivityKind,
        *,
        body: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.db.add(
            Activity(
                organization_id=self.org,
                subject_type=subject_type,
                subject_id=subject_id,
                kind=kind,
                body=body,
                details=details or {},
                actor_user_id=self.workspace.user.id,
                request_id=request_id_var.get(),
            )
        )

    async def _audit(
        self, action: str, target_type: str, target_id: uuid.UUID, details: dict[str, Any]
    ) -> None:
        await record_workspace_audit(
            self.db,
            self.workspace,
            action=action,
            target_type=target_type,
            target_id=target_id,
            details=details,
        )

    async def _record(
        self,
        subject_type: SubjectType,
        subject_id: uuid.UUID,
        kind: ActivityKind,
        details: dict[str, Any],
    ) -> None:
        self._activity(subject_type, subject_id, kind, details=details)
        await self._audit(
            f"crm.{subject_type.value}.{kind.value}", subject_type, subject_id, details
        )

    async def _flush(self) -> None:
        """Flush, turning a lost race on the identity indexes into a 409 like the pre-check."""
        try:
            await self.db.flush()
        except IntegrityError as exc:
            constraint = getattr(getattr(exc.orig, "diag", None), "constraint_name", None)
            field = UNIQUE_IDENTITY_INDEXES.get(constraint or "")
            if field is None:
                raise
            raise DuplicateContactError(
                details=[ErrorDetail(loc=["body", field], msg="Already used.", type="duplicate")]
            ) from exc

    # --- customers -------------------------------------------------------------------------

    async def get_customer(self, customer_id: uuid.UUID) -> Customer:
        customer = await self.customers.get(customer_id)
        if customer is None:
            raise NotFoundError("Customer not found.")
        return customer

    async def _active_customer(self, customer_id: uuid.UUID, field: str) -> Customer:
        """A customer referenced from input; another tenant's id behaves like a missing one."""
        customer = await self.customers.get(customer_id)
        if customer is None:
            raise ValidationFailedError(
                "Customer not found.",
                details=[ErrorDetail(loc=["body", field], msg="Not found.", type="not_found")],
            )
        if customer.archived_at is not None:
            raise ConflictError("The customer is archived.")
        return customer

    async def list_customers(
        self, *, q: str | None, include_archived: bool, limit: int, cursor: str | None
    ) -> tuple[list[Customer], str | None]:
        query = select(Customer).where(Customer.organization_id == self.org)
        if not include_archived:
            query = query.where(Customer.archived_at.is_(None))
        if q:
            pattern = _like(q)
            query = query.where(
                or_(
                    Customer.name.ilike(pattern, escape="\\"),
                    Customer.vat_number.ilike(pattern, escape="\\"),
                )
            )
        query = paginate(query, Customer.created_at, Customer.id, limit=limit, cursor=cursor)
        rows = list((await self.db.scalars(query)).all())
        return _page(rows, limit, lambda c: (c.created_at, c.id))

    async def create_customer(self, body: schemas.CustomerCreate) -> Customer:
        customer = await self.customers.add(
            created_by_user_id=self.workspace.user.id, **body.model_dump()
        )
        await self._record(SubjectType.CUSTOMER, customer.id, ActivityKind.CREATED, {})
        return customer

    async def update_customer(
        self, customer_id: uuid.UUID, body: schemas.CustomerUpdate
    ) -> Customer:
        customer = await self.get_customer(customer_id)
        values = body.model_dump(exclude_unset=True)
        for required in ("kind", "name"):
            if required in values and values[required] is None:
                del values[required]
        changes = _changes(customer, values)
        if changes:
            for key, value in changes.items():
                setattr(customer, key, value)
            await self._flush()
            details = {"fields": sorted(changes)}
            await self._record(SubjectType.CUSTOMER, customer.id, ActivityKind.UPDATED, details)
        return customer

    async def set_customer_archived(self, customer_id: uuid.UUID, archived: bool) -> Customer:
        customer = await self.get_customer(customer_id)
        if (customer.archived_at is not None) != archived:
            customer.archived_at = datetime.now(UTC) if archived else None
            await self._flush()
            kind = ActivityKind.ARCHIVED if archived else ActivityKind.RESTORED
            await self._record(SubjectType.CUSTOMER, customer.id, kind, {})
        return customer

    # --- contacts --------------------------------------------------------------------------

    def _contact_query(self) -> Select[Contact, Customer]:
        return (
            select(Contact, Customer)
            .outerjoin(
                Customer,
                (Customer.id == Contact.customer_id)
                & (Customer.organization_id == Contact.organization_id),
            )
            .where(Contact.organization_id == self.org)
        )

    async def contact_out(self, contact: Contact) -> schemas.ContactOut:
        customer = await self.customers.get(contact.customer_id) if contact.customer_id else None
        return _contact_out(contact, customer)

    async def get_contact(self, contact_id: uuid.UUID) -> Contact:
        contact = await self.contacts.get(contact_id)
        if contact is None:
            raise NotFoundError("Contact not found.")
        return contact

    async def list_contacts(
        self,
        *,
        q: str | None,
        customer_id: uuid.UUID | None,
        include_archived: bool,
        limit: int,
        cursor: str | None,
    ) -> tuple[list[schemas.ContactOut], str | None]:
        query = self._contact_query()
        if not include_archived:
            query = query.where(Contact.archived_at.is_(None))
        if customer_id is not None:
            query = query.where(Contact.customer_id == customer_id)
        if q:
            pattern = _like(q)
            query = query.where(
                or_(
                    Contact.full_name.ilike(pattern, escape="\\"),
                    Contact.email.ilike(pattern, escape="\\"),
                    Contact.phone.ilike(pattern, escape="\\"),
                )
            )
        query = paginate(query, Contact.created_at, Contact.id, limit=limit, cursor=cursor)
        rows = list((await self.db.execute(query)).all())
        page, next_cursor = _page(rows, limit, lambda r: (r[0].created_at, r[0].id))
        return [_contact_out(c, cu) for c, cu in page], next_cursor

    async def _ensure_unique_identity(
        self, email: str | None, phone: str | None, exclude: uuid.UUID | None = None
    ) -> None:
        checks = [("email", Contact.email, email), ("phone", Contact.phone, phone)]
        details: list[ErrorDetail] = []
        for field, column, value in checks:
            if value is None:
                continue
            query = select(Contact.id).where(Contact.organization_id == self.org, column == value)
            if exclude is not None:
                query = query.where(Contact.id != exclude)
            existing = await self.db.scalar(query)
            if existing is not None:
                details.append(
                    ErrorDetail(
                        loc=["body", field],
                        msg="Already used by another contact.",
                        type="duplicate",
                        ref=str(existing),
                    )
                )
        if details:
            raise DuplicateContactError(details=details)

    async def create_contact(self, body: schemas.ContactCreate) -> Contact:
        if body.email is None and body.phone is None:
            raise _identity_required()
        await self._ensure_unique_identity(body.email, body.phone)
        if body.customer_id is not None:
            await self._active_customer(body.customer_id, "customer_id")
        contact = Contact(
            organization_id=self.org,
            created_by_user_id=self.workspace.user.id,
            **body.model_dump(),
        )
        self.db.add(contact)
        await self._flush()
        await self._record(SubjectType.CONTACT, contact.id, ActivityKind.CREATED, {})
        return contact

    async def update_contact(self, contact_id: uuid.UUID, body: schemas.ContactUpdate) -> Contact:
        contact = await self.get_contact(contact_id)
        values = body.model_dump(exclude_unset=True)
        if "full_name" in values and values["full_name"] is None:
            del values["full_name"]
        changes = _changes(contact, values)
        if not changes:
            return contact
        email = changes.get("email", contact.email)
        phone = changes.get("phone", contact.phone)
        if email is None and phone is None:
            raise _identity_required()
        await self._ensure_unique_identity(
            changes.get("email"), changes.get("phone"), exclude=contact.id
        )
        if changes.get("customer_id") is not None:
            await self._active_customer(changes["customer_id"], "customer_id")
        for key, value in changes.items():
            setattr(contact, key, value)
        await self._flush()
        details = {"fields": sorted(changes)}
        await self._record(SubjectType.CONTACT, contact.id, ActivityKind.UPDATED, details)
        return contact

    async def set_contact_archived(self, contact_id: uuid.UUID, archived: bool) -> Contact:
        contact = await self.get_contact(contact_id)
        if (contact.archived_at is not None) != archived:
            contact.archived_at = datetime.now(UTC) if archived else None
            await self._flush()
            kind = ActivityKind.ARCHIVED if archived else ActivityKind.RESTORED
            await self._record(SubjectType.CONTACT, contact.id, kind, {})
        return contact

    # --- leads -----------------------------------------------------------------------------

    def _lead_query(self) -> Select[Lead, str, str, str]:
        return (
            select(Lead, Contact.full_name, Customer.name, User.display_name)
            .join(
                Contact,
                (Contact.id == Lead.contact_id) & (Contact.organization_id == Lead.organization_id),
            )
            .outerjoin(
                Customer,
                (Customer.id == Lead.customer_id)
                & (Customer.organization_id == Lead.organization_id),
            )
            .outerjoin(User, User.id == Lead.owner_user_id)
            .where(Lead.organization_id == self.org)
        )

    async def get_lead(self, lead_id: uuid.UUID) -> Lead:
        lead = await self.leads.get(lead_id)
        if lead is None:
            raise NotFoundError("Lead not found.")
        return lead

    async def _locked_lead(self, lead_id: uuid.UUID) -> Lead:
        # Refresh after waiting for any competing transition/archive to commit. Keep the lock
        # until the request transaction commits its state, activity and audit together.
        lead = await self.db.scalar(
            select(Lead)
            .where(Lead.organization_id == self.org, Lead.id == lead_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if lead is None:
            raise NotFoundError("Lead not found.")
        return lead

    async def lead_out(self, lead_id: uuid.UUID) -> schemas.LeadOut:
        row = (await self.db.execute(self._lead_query().where(Lead.id == lead_id))).first()
        if row is None:
            raise NotFoundError("Lead not found.")
        return _lead_out(*row)

    async def list_leads(
        self,
        *,
        q: str | None,
        status: LeadStatus | None,
        contact_id: uuid.UUID | None,
        customer_id: uuid.UUID | None,
        owner_user_id: uuid.UUID | None,
        include_archived: bool,
        limit: int,
        cursor: str | None,
    ) -> tuple[list[schemas.LeadOut], str | None]:
        query = self._lead_query()
        if not include_archived:
            query = query.where(Lead.archived_at.is_(None))
        filters = {
            Lead.status: status,
            Lead.contact_id: contact_id,
            Lead.customer_id: customer_id,
            Lead.owner_user_id: owner_user_id,
        }
        for column, value in filters.items():
            if value is not None:
                query = query.where(column == value)
        if q:
            pattern = _like(q)
            query = query.where(
                or_(
                    Lead.title.ilike(pattern, escape="\\"),
                    Contact.full_name.ilike(pattern, escape="\\"),
                )
            )
        query = paginate(query, Lead.created_at, Lead.id, limit=limit, cursor=cursor)
        rows = list((await self.db.execute(query)).all())
        page, next_cursor = _page(rows, limit, lambda r: (r[0].created_at, r[0].id))
        return [_lead_out(*row) for row in page], next_cursor

    async def _ensure_member(self, user_id: uuid.UUID) -> None:
        is_member = await self.db.scalar(
            select(Membership.id).where(
                Membership.organization_id == self.org, Membership.user_id == user_id
            )
        )
        if is_member is None:
            raise ValidationFailedError(
                "The lead owner must be a member of this workspace.",
                details=[
                    ErrorDetail(loc=["body", "owner_user_id"], msg="Not a member.", type="invalid")
                ],
            )

    async def create_lead(self, body: schemas.LeadCreate) -> Lead:
        contact = await self.contacts.get(body.contact_id)
        if contact is None:
            raise ValidationFailedError(
                "Contact not found.",
                details=[
                    ErrorDetail(loc=["body", "contact_id"], msg="Not found.", type="not_found")
                ],
            )
        if contact.archived_at is not None:
            raise ConflictError("The contact is archived.")
        customer_id = body.customer_id or contact.customer_id
        if body.customer_id is not None:
            await self._active_customer(body.customer_id, "customer_id")
        if body.owner_user_id is not None:
            await self._ensure_member(body.owner_user_id)
        values = body.model_dump(exclude={"customer_id"})
        lead = await self.leads.add(
            customer_id=customer_id,
            status=LeadStatus.NEW,
            created_by_user_id=self.workspace.user.id,
            **values,
        )
        details = {"source": lead.source.value, "contact_id": str(contact.id)}
        await self._record(SubjectType.LEAD, lead.id, ActivityKind.CREATED, details)
        return lead

    async def update_lead(self, lead_id: uuid.UUID, body: schemas.LeadUpdate) -> Lead:
        lead = await self.get_lead(lead_id)
        values = body.model_dump(exclude_unset=True)
        for required in ("title", "source"):
            if required in values and values[required] is None:
                del values[required]
        changes = _changes(lead, values)
        if changes.get("customer_id") is not None:
            await self._active_customer(changes["customer_id"], "customer_id")
        if changes.get("owner_user_id") is not None:
            await self._ensure_member(changes["owner_user_id"])
        if changes:
            for key, value in changes.items():
                setattr(lead, key, value)
            await self._flush()
            details = {"fields": sorted(changes)}
            await self._record(SubjectType.LEAD, lead.id, ActivityKind.UPDATED, details)
        return lead

    async def change_lead_status(self, lead_id: uuid.UUID, body: schemas.LeadStatusChange) -> Lead:
        lead = await self._locked_lead(lead_id)
        if lead.archived_at is not None:
            raise ConflictError("The lead is archived. Restore it before changing its status.")
        current = lead.status
        if not can_transition(current, body.status):
            allowed = ", ".join(allowed_transitions(current)) or "none"
            raise ConflictError(
                f"A {current.value} lead cannot move to {body.status.value} (allowed: {allowed})."
            )
        if body.status is LeadStatus.LOST and body.lost_reason is None:
            raise ValidationFailedError(
                "A reason is required to mark a lead as lost.",
                details=[ErrorDetail(loc=["body", "lost_reason"], msg="Required.", type="missing")],
            )
        lead.status = body.status
        lead.lost_reason = body.lost_reason if body.status is LeadStatus.LOST else None
        lead.status_changed_at = datetime.now(UTC)
        await self._flush()
        details = {"from": current.value, "to": body.status.value}
        await self._record(SubjectType.LEAD, lead.id, ActivityKind.STATUS_CHANGED, details)
        return lead

    async def set_lead_archived(self, lead_id: uuid.UUID, archived: bool) -> Lead:
        lead = await self._locked_lead(lead_id)
        if (lead.archived_at is not None) != archived:
            lead.archived_at = datetime.now(UTC) if archived else None
            await self._flush()
            kind = ActivityKind.ARCHIVED if archived else ActivityKind.RESTORED
            await self._record(SubjectType.LEAD, lead.id, kind, {})
        return lead

    # --- activities ------------------------------------------------------------------------

    async def _ensure_subject(self, subject_type: SubjectType, subject_id: uuid.UUID) -> None:
        if subject_type is SubjectType.CUSTOMER:
            await self.get_customer(subject_id)
        elif subject_type is SubjectType.CONTACT:
            await self.get_contact(subject_id)
        else:
            await self.get_lead(subject_id)

    async def list_activities(
        self,
        subject_type: SubjectType,
        subject_id: uuid.UUID,
        *,
        limit: int,
        cursor: str | None,
    ) -> tuple[list[schemas.ActivityOut], str | None]:
        await self._ensure_subject(subject_type, subject_id)
        query = (
            select(Activity, User.display_name)
            .outerjoin(User, User.id == Activity.actor_user_id)
            .where(
                Activity.organization_id == self.org,
                Activity.subject_type == subject_type,
                Activity.subject_id == subject_id,
            )
        )
        query = paginate(query, Activity.occurred_at, Activity.id, limit=limit, cursor=cursor)
        rows = list((await self.db.execute(query)).all())
        page, next_cursor = _page(rows, limit, lambda r: (r[0].occurred_at, r[0].id))
        return [_activity_out(activity, name) for activity, name in page], next_cursor

    async def add_note(self, body: schemas.NoteCreate) -> schemas.ActivityOut:
        await self._ensure_subject(body.subject_type, body.subject_id)
        note = Activity(
            organization_id=self.org,
            subject_type=body.subject_type,
            subject_id=body.subject_id,
            kind=ActivityKind.NOTE,
            body=body.body,
            details={},
            actor_user_id=self.workspace.user.id,
            request_id=request_id_var.get(),
        )
        self.db.add(note)
        await self.db.flush()
        return _activity_out(note, self.workspace.user.display_name)

    # --- import ----------------------------------------------------------------------------

    async def import_contacts(
        self, body: schemas.ContactImportRequest
    ) -> schemas.ContactImportResult:
        try:
            parsed = parse_contacts_csv(body.csv)
        except ImportFileError as exc:
            raise ValidationFailedError(
                str(exc),
                details=[ErrorDetail(loc=["body", "csv"], msg=str(exc), type="invalid_file")],
            ) from exc

        duplicates = [
            schemas.ImportDuplicate(row=row, field=field, existing_contact_id=None, first_row=first)
            for row, field, first in parsed.file_duplicates
        ]
        by_email, by_phone = await self._existing_identities(
            {r.email for r in parsed.rows if r.email}, {r.phone for r in parsed.rows if r.phone}
        )
        rows: list[ImportRow] = []
        for row in parsed.rows:
            if row.email is not None and row.email in by_email:
                hit: tuple[str, uuid.UUID] | None = ("email", by_email[row.email])
            elif row.phone is not None and row.phone in by_phone:
                hit = ("phone", by_phone[row.phone])
            else:
                hit = None
            if hit is not None:
                duplicates.append(
                    schemas.ImportDuplicate(
                        row=row.row, field=hit[0], existing_contact_id=hit[1], first_row=None
                    )
                )
            else:
                rows.append(row)

        customer_ids = await self._existing_customers({r.company for r in rows if r.company})
        new_companies: dict[str, str] = {}
        for row in rows:
            if row.company and row.company.lower() not in customer_ids:
                new_companies.setdefault(row.company.lower(), row.company)
        leads = [r for r in rows if r.lead_title]

        if not body.dry_run and rows:
            await self._write_import(rows, customer_ids, new_companies)

        result = schemas.ContactImportResult(
            dry_run=body.dry_run,
            total=parsed.total,
            contacts_created=len(rows),
            customers_created=len(new_companies),
            leads_created=len(leads),
            duplicates=sorted(duplicates, key=lambda d: d.row),
            errors=[
                schemas.ImportRowError(row=e.row, field=e.field, message=e.message)
                for e in parsed.errors
            ],
        )
        if not body.dry_run:
            await self._audit(
                "crm.contacts.imported",
                "organization",
                self.org,
                {
                    "total": result.total,
                    "contacts_created": result.contacts_created,
                    "customers_created": result.customers_created,
                    "leads_created": result.leads_created,
                    "duplicates": len(result.duplicates),
                    "errors": len(result.errors),
                },
            )
        return result

    async def _existing_identities(
        self, emails: set[str], phones: set[str]
    ) -> tuple[dict[str, uuid.UUID], dict[str, uuid.UUID]]:
        if not emails and not phones:
            return {}, {}
        rows = await self.db.execute(
            select(Contact.id, Contact.email, Contact.phone).where(
                Contact.organization_id == self.org,
                or_(Contact.email.in_(emails), Contact.phone.in_(phones)),
            )
        )
        by_email: dict[str, uuid.UUID] = {}
        by_phone: dict[str, uuid.UUID] = {}
        for contact_id, email, phone in rows:
            if email is not None:
                by_email[email.lower()] = contact_id
            if phone is not None:
                by_phone[phone] = contact_id
        return by_email, by_phone

    async def _existing_customers(self, names: Iterable[str]) -> dict[str, uuid.UUID]:
        lowered = {n.lower() for n in names}
        if not lowered:
            return {}
        rows = await self.db.execute(
            select(Customer.id, Customer.name)
            .where(
                Customer.organization_id == self.org,
                Customer.archived_at.is_(None),
                func.lower(Customer.name).in_(lowered),
            )
            .order_by(Customer.created_at)
        )
        found: dict[str, uuid.UUID] = {}
        for customer_id, name in rows:
            found.setdefault(name.lower(), customer_id)
        return found

    async def _write_import(
        self,
        rows: list[ImportRow],
        customer_ids: dict[str, uuid.UUID],
        new_companies: dict[str, str],
    ) -> None:
        user_id = self.workspace.user.id
        imported = {"via": "csv"}
        customers = {
            key: Customer(
                id=uuid.uuid4(),
                organization_id=self.org,
                kind=CustomerKind.BUSINESS,
                name=name,
                created_by_user_id=user_id,
            )
            for key, name in new_companies.items()
        }
        self.db.add_all(customers.values())
        await self.db.flush()
        for customer in customers.values():
            customer_ids[customer.name.lower()] = customer.id
            self._activity(
                SubjectType.CUSTOMER, customer.id, ActivityKind.IMPORTED, details=imported
            )

        contacts = []
        for row in rows:
            contact = Contact(
                id=uuid.uuid4(),
                organization_id=self.org,
                customer_id=customer_ids.get(row.company.lower()) if row.company else None,
                full_name=row.full_name,
                email=row.email,
                phone=row.phone,
                notes=row.notes,
                created_by_user_id=user_id,
            )
            contacts.append((row, contact))
        self.db.add_all([c for _, c in contacts])
        await self._flush()

        for row, contact in contacts:
            self._activity(SubjectType.CONTACT, contact.id, ActivityKind.IMPORTED, details=imported)
            if row.lead_title:
                lead = Lead(
                    id=uuid.uuid4(),
                    organization_id=self.org,
                    contact_id=contact.id,
                    customer_id=contact.customer_id,
                    title=row.lead_title,
                    source=LeadSource.IMPORT,
                    status=LeadStatus.NEW,
                    created_by_user_id=user_id,
                )
                self.db.add(lead)
                self._activity(
                    SubjectType.LEAD,
                    lead.id,
                    ActivityKind.CREATED,
                    details={"source": LeadSource.IMPORT.value, "contact_id": str(contact.id)},
                )
        await self.db.flush()


def _identity_required() -> ValidationFailedError:
    return ValidationFailedError(
        "An email or a phone number is required.",
        details=[
            ErrorDetail(loc=["body", "email"], msg="Email or phone required.", type="missing"),
            ErrorDetail(loc=["body", "phone"], msg="Email or phone required.", type="missing"),
        ],
    )


def customer_out(customer: Customer) -> schemas.CustomerOut:
    return schemas.CustomerOut(
        id=customer.id,
        kind=customer.kind,
        name=customer.name,
        vat_number=customer.vat_number,
        notes=customer.notes,
        created_at=customer.created_at,
        updated_at=customer.updated_at,
        archived_at=customer.archived_at,
    )


def _contact_out(contact: Contact, customer: Customer | None) -> schemas.ContactOut:
    return schemas.ContactOut(
        id=contact.id,
        full_name=contact.full_name,
        email=contact.email,
        phone=contact.phone,
        customer=schemas.CustomerRef(id=customer.id, name=customer.name) if customer else None,
        notes=contact.notes,
        created_at=contact.created_at,
        updated_at=contact.updated_at,
        archived_at=contact.archived_at,
    )


def _lead_out(
    lead: Lead, contact_name: str, customer_name: str | None, owner_name: str | None
) -> schemas.LeadOut:
    return schemas.LeadOut(
        id=lead.id,
        title=lead.title,
        status=lead.status,
        source=lead.source,
        contact=schemas.ContactRef(id=lead.contact_id, full_name=contact_name),
        customer=(
            schemas.CustomerRef(id=lead.customer_id, name=customer_name)
            if lead.customer_id is not None and customer_name is not None
            else None
        ),
        owner=(
            schemas.UserRef(user_id=lead.owner_user_id, display_name=owner_name)
            if lead.owner_user_id is not None
            else None
        ),
        notes=lead.notes,
        lost_reason=lead.lost_reason,
        status_changed_at=lead.status_changed_at,
        archived_at=lead.archived_at,
        created_at=lead.created_at,
        updated_at=lead.updated_at,
        allowed_transitions=allowed_transitions(lead.status) if lead.archived_at is None else [],
    )


def _activity_out(activity: Activity, actor_name: str | None) -> schemas.ActivityOut:
    return schemas.ActivityOut(
        id=activity.id,
        subject_type=activity.subject_type,
        subject_id=activity.subject_id,
        kind=activity.kind,
        body=activity.body,
        details=activity.details,
        actor=(
            schemas.UserRef(user_id=activity.actor_user_id, display_name=actor_name)
            if activity.actor_user_id is not None
            else None
        ),
        occurred_at=activity.occurred_at,
    )
