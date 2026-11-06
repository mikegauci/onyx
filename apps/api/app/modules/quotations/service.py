"""Quotation domain service: the only code that changes quotation rows.

Every method runs inside the request transaction, bound to the caller's workspace. The tenant
comes from ``WorkspaceAccess`` (never from input); queries add an explicit ``organization_id``
filter on top of row-level security. Every write locks the quote row first, so concurrent
edits and approvals see the latest committed state. Each change writes an audit entry in the
same transaction.

Totals are computed only by ``pricing.py``. CRM and catalogue data are read only through their
public interfaces (``crm.public``, ``catalogue.public``).
"""

import uuid
from collections.abc import Sequence
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import func, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit.record import record_workspace_audit
from app.core.auth.deps import WorkspaceAccess
from app.core.auth.permissions import Permission, has_permission
from app.core.errors import ConflictError, ErrorDetail, NotFoundError, ValidationFailedError
from app.core.tenancy.models import User
from app.modules.catalogue import public as catalogue
from app.modules.crm import public as crm
from app.modules.crm.pagination import encode_cursor, paginate
from app.modules.quotations import schemas
from app.modules.quotations.models import (
    Counter,
    Line,
    LineKind,
    Quote,
    QuoteStatus,
    Settings,
    Version,
    VersionStatus,
)
from app.modules.quotations.pricing import (
    LineInput,
    QuoteTotals,
    format_minor,
    line_totals,
    quote_totals,
)
from app.modules.quotations.rules import LineWarning, allowed_actions, can, line_warnings

DEFAULT_PREFIX = "Q"
DEFAULT_VALIDITY_DAYS = 30
DEFAULT_MAX_DISCOUNT = Decimal("10.00")


class StateError(ConflictError):
    default_message = "This quote cannot be changed in its current state."


class ApprovalBlockedError(ConflictError):
    default_message = "The quote has warnings that block approval."


def _invalid(field: str, message: str, kind: str = "invalid") -> ValidationFailedError:
    return ValidationFailedError(
        message, details=[ErrorDetail(loc=["body", field], msg=message, type=kind)]
    )


def money(minor: int) -> schemas.Money:
    return schemas.Money(minor=minor, amount=format_minor(minor))


def parse_amount(value: str) -> int:
    whole, _, cents = value.partition(".")
    return int(whole) * 100 + int((cents + "00")[:2])


def _like(term: str) -> str:
    escaped = term.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _input(line: Line) -> LineInput:
    return LineInput(
        unit_price_minor=line.unit_price_minor,
        quantity=line.quantity,
        discount_percent=line.discount_percent,
        vat_code=line.vat_code,
        vat_percent=line.vat_percent,
    )


def _apply_totals(line: Line, prices_include_vat: bool) -> None:
    totals = line_totals(_input(line), prices_include_vat=prices_include_vat)
    line.net_minor, line.vat_minor, line.gross_minor = (
        totals.net_minor,
        totals.vat_minor,
        totals.gross_minor,
    )


def _line_out(line: Line, prices_include_vat: bool) -> schemas.LineOut:
    t = line_totals(_input(line), prices_include_vat=prices_include_vat)
    return schemas.LineOut(
        id=line.id,
        position=line.position,
        kind=line.kind,
        variant_id=line.variant_id,
        sku=line.sku,
        description=line.description,
        quantity=line.quantity,
        unit_price=money(line.unit_price_minor),
        price_valid_from=line.price_valid_from,
        vat_code=line.vat_code,
        vat_percent=line.vat_percent,
        discount_percent=line.discount_percent,
        list_total=money(t.list_minor),
        discount=money(t.discount_minor),
        net=money(t.net_minor),
        vat=money(t.vat_minor),
        gross=money(t.gross_minor),
    )


def _totals_out(totals: QuoteTotals) -> schemas.TotalsOut:
    return schemas.TotalsOut(
        list_total=money(totals.list_minor),
        discount=money(totals.discount_minor),
        net=money(totals.net_minor),
        vat=money(totals.vat_minor),
        gross=money(totals.gross_minor),
        vat_breakdown=[
            schemas.VatGroupOut(
                code=g.code,
                rate_percent=g.rate_percent,
                net=money(g.net_minor),
                vat=money(g.vat_minor),
            )
            for g in totals.vat_breakdown
        ],
    )


def _warning_out(warning: LineWarning) -> schemas.WarningOut:
    return schemas.WarningOut(
        line_id=warning.line_id,
        code=warning.code,
        blocking=warning.blocking,
        message=warning.message,
        current=warning.current,
    )


def workspace_today(workspace: WorkspaceAccess) -> date:
    """Today in the workspace's timezone: the date quote validity is judged by."""
    try:
        zone = ZoneInfo(workspace.organization.timezone)
    except (KeyError, ValueError):
        zone = ZoneInfo("UTC")
    return datetime.now(UTC).astimezone(zone).date()


class QuotationService:
    def __init__(self, db: AsyncSession, workspace: WorkspaceAccess) -> None:
        self.db = db
        self.workspace = workspace
        self.tenant = workspace.tenant
        self.org = workspace.tenant.organization_id
        self.actor = workspace.user.id

    # --- shared ----------------------------------------------------------------------------

    async def _audit(self, action: str, quote_id: uuid.UUID, details: dict[str, Any]) -> None:
        await record_workspace_audit(
            self.db,
            self.workspace,
            action=f"quotations.{action}",
            target_type="quote",
            target_id=quote_id,
            details=details,
        )

    def _today(self) -> date:
        return workspace_today(self.workspace)

    def _can_approve(self) -> bool:
        return has_permission(self.workspace.role, Permission.QUOTATIONS_APPROVE)

    # --- settings --------------------------------------------------------------------------

    async def settings(self) -> schemas.SettingsOut:
        row = await self.db.scalar(select(Settings).where(Settings.organization_id == self.org))
        if row is None:
            return schemas.SettingsOut(
                number_prefix=DEFAULT_PREFIX,
                validity_days=DEFAULT_VALIDITY_DAYS,
                max_discount_percent=DEFAULT_MAX_DISCOUNT,
            )
        return schemas.SettingsOut(
            number_prefix=row.number_prefix,
            validity_days=row.validity_days,
            max_discount_percent=row.max_discount_percent,
        )

    async def update_settings(self, body: schemas.SettingsUpdate) -> schemas.SettingsOut:
        current = await self.settings()
        values = {
            "number_prefix": body.number_prefix or current.number_prefix,
            "validity_days": body.validity_days or current.validity_days,
            "max_discount_percent": current.max_discount_percent
            if body.max_discount_percent is None
            else body.max_discount_percent,
        }
        await self.db.execute(
            insert(Settings)
            .values(organization_id=self.org, updated_by_user_id=self.actor, **values)
            .on_conflict_do_update(
                index_elements=[Settings.organization_id],
                set_={**values, "updated_by_user_id": self.actor, "updated_at": func.now()},
            )
        )
        await record_workspace_audit(
            self.db,
            self.workspace,
            action="quotations.settings.updated",
            target_type="organization",
            target_id=self.org,
            details={k: str(v) for k, v in values.items()},
        )
        return schemas.SettingsOut(**values)

    async def _next_number(self, prefix: str) -> str:
        year = self._today().year
        number = await self.db.scalar(
            insert(Counter)
            .values(organization_id=self.org, year=year, last_number=1)
            .on_conflict_do_update(
                index_elements=[Counter.organization_id, Counter.year],
                set_={"last_number": Counter.last_number + 1},
            )
            .returning(Counter.last_number)
        )
        return f"{prefix}-{year}-{int(number or 0):04d}"

    # --- loading ---------------------------------------------------------------------------

    async def _quote(self, quote_id: uuid.UUID, *, lock: bool = False) -> Quote:
        query = select(Quote).where(Quote.organization_id == self.org, Quote.id == quote_id)
        if lock:
            query = query.with_for_update().execution_options(populate_existing=True)
        quote = await self.db.scalar(query)
        if quote is None:
            raise NotFoundError("Quote not found.")
        return quote

    async def _version(self, quote: Quote, number: int | None = None) -> Version:
        version = await self.db.scalar(
            select(Version).where(
                Version.organization_id == self.org,
                Version.quote_id == quote.id,
                Version.version == (number or quote.current_version),
            )
        )
        if version is None:
            raise NotFoundError("Quote version not found.")
        return version

    async def _lines(self, version: Version) -> list[Line]:
        return list(
            (
                await self.db.scalars(
                    select(Line)
                    .where(Line.organization_id == self.org, Line.version_id == version.id)
                    .order_by(Line.position, Line.id)
                )
            ).all()
        )

    async def _draft(self, quote_id: uuid.UUID) -> tuple[Quote, Version]:
        quote = await self._quote(quote_id, lock=True)
        if not can(quote.status, "edit"):
            raise StateError("Only a draft quote can be edited. Revise it to make changes.")
        return quote, await self._version(quote)

    async def _line(self, version: Version, line_id: uuid.UUID) -> Line:
        line = await self.db.scalar(
            select(Line).where(
                Line.organization_id == self.org,
                Line.version_id == version.id,
                Line.id == line_id,
            )
        )
        if line is None:
            raise NotFoundError("Line not found.")
        return line

    async def warnings(self, quote: Quote, lines: Sequence[Line]) -> list[LineWarning]:
        ids = [line.variant_id for line in lines if line.variant_id]
        skus = await catalogue.get_skus(self.db, self.tenant, ids, quote.price_list_id)
        found: list[LineWarning] = []
        for line in lines:
            sku = skus.get(line.variant_id) if line.variant_id else None
            found.extend(line_warnings(line, sku))
        return found

    # --- reading ---------------------------------------------------------------------------

    async def list_quotes(
        self,
        *,
        status: QuoteStatus | None,
        contact_id: uuid.UUID | None,
        q: str | None,
        limit: int,
        cursor: str | None,
    ) -> tuple[list[schemas.QuoteSummary], str | None]:
        query = select(Quote).where(Quote.organization_id == self.org)
        if status is not None:
            query = query.where(Quote.status == status)
        if contact_id is not None:
            query = query.where(Quote.contact_id == contact_id)
        if q:
            pattern = _like(q)
            query = query.where(
                or_(
                    Quote.number.ilike(pattern, escape="\\"),
                    Quote.title.ilike(pattern, escape="\\"),
                )
            )
        query = paginate(query, Quote.updated_at, Quote.id, limit=limit, cursor=cursor)
        rows = list((await self.db.scalars(query)).all())
        page = rows[:limit]
        next_cursor = encode_cursor(page[-1].updated_at, page[-1].id) if len(rows) > limit else None
        contacts = await crm.get_contacts(self.db, self.tenant, [r.contact_id for r in page])
        versions = {
            (v.quote_id, v.version): v
            for v in (
                await self.db.scalars(
                    select(Version).where(
                        Version.organization_id == self.org,
                        Version.quote_id.in_([r.id for r in page]),
                    )
                )
            ).all()
        }
        items = []
        for quote in page:
            version = versions[(quote.id, quote.current_version)]
            if version.gross_minor is not None:
                gross = version.gross_minor
            else:
                gross = (await self._compute(version)).gross_minor
            contact = contacts.get(quote.contact_id)
            items.append(
                schemas.QuoteSummary(
                    id=quote.id,
                    number=quote.number,
                    title=quote.title,
                    status=quote.status,
                    contact=schemas.Ref(
                        id=quote.contact_id, label=contact.full_name if contact else "—"
                    ),
                    current_version=quote.current_version,
                    gross=money(gross),
                    updated_at=quote.updated_at,
                )
            )
        return items, next_cursor

    async def _compute(self, version: Version) -> QuoteTotals:
        lines = await self._lines(version)
        return quote_totals(
            (_input(x) for x in lines), prices_include_vat=version.prices_include_vat
        )

    async def _user_ref(self, user_id: uuid.UUID | None) -> schemas.Ref | None:
        if user_id is None:
            return None
        name = await self.db.scalar(select(User.display_name).where(User.id == user_id))
        return schemas.Ref(id=user_id, label=name or "Former member")

    async def detail(
        self, quote_id: uuid.UUID, version_number: int | None = None
    ) -> schemas.QuoteDetail:
        quote = await self._quote(quote_id)
        version = await self._version(quote, version_number)
        lines = await self._lines(version)
        totals = quote_totals(
            (_input(x) for x in lines), prices_include_vat=version.prices_include_vat
        )
        draft = version.status is VersionStatus.DRAFT and quote.status is QuoteStatus.DRAFT
        warnings = await self.warnings(quote, lines) if draft else []
        contact = (await crm.get_contacts(self.db, self.tenant, [quote.contact_id])).get(
            quote.contact_id
        )
        customer = (
            await crm.get_customer(self.db, self.tenant, quote.customer_id)
            if quote.customer_id
            else None
        )
        lead = await crm.get_lead(self.db, self.tenant, quote.lead_id) if quote.lead_id else None
        price_list = await catalogue.get_price_list(self.db, self.tenant, quote.price_list_id)
        all_versions = (
            await self.db.scalars(
                select(Version)
                .where(Version.organization_id == self.org, Version.quote_id == quote.id)
                .order_by(Version.version.desc())
            )
        ).all()
        settings = await self.settings()
        return schemas.QuoteDetail(
            id=quote.id,
            number=quote.number,
            title=quote.title,
            status=quote.status,
            contact=schemas.Ref(id=quote.contact_id, label=contact.full_name if contact else "—"),
            customer=schemas.Ref(id=customer.id, label=customer.name) if customer else None,
            lead=schemas.Ref(id=lead.id, label=lead.title) if lead else None,
            price_list=schemas.Ref(
                id=quote.price_list_id,
                label=f"{price_list.name} ({price_list.code})" if price_list else "—",
            ),
            prices_include_vat=version.prices_include_vat,
            version=version.version,
            version_status=version.status,
            notes=version.notes,
            valid_until=version.valid_until,
            lines=[_line_out(x, version.prices_include_vat) for x in lines],
            totals=_totals_out(totals),
            warnings=[_warning_out(w) for w in warnings],
            acknowledged_warnings=version.acknowledged_warnings,
            max_discount_percent=settings.max_discount_percent,
            allowed_actions=allowed_actions(quote.status)
            if version.version == quote.current_version
            else [],
            outcome_reason=quote.outcome_reason,
            approved_at=version.approved_at,
            approved_by=await self._user_ref(version.approved_by_user_id),
            versions=[
                schemas.VersionSummary(
                    version=v.version,
                    status=v.status,
                    gross=money(v.gross_minor) if v.gross_minor is not None else None,
                    approved_at=v.approved_at,
                    approved_by=await self._user_ref(v.approved_by_user_id),
                    created_at=v.created_at,
                )
                for v in all_versions
            ],
            created_at=quote.created_at,
            updated_at=quote.updated_at,
        )

    async def for_pdf(self, quote_id: uuid.UUID, version_number: int) -> schemas.QuoteDetail:
        return await self.detail(quote_id, version_number)

    # --- quotes ----------------------------------------------------------------------------

    async def create_quote(self, body: schemas.QuoteCreate) -> uuid.UUID:
        contact = (await crm.get_contacts(self.db, self.tenant, [body.contact_id])).get(
            body.contact_id
        )
        if contact is None:
            raise _invalid("contact_id", "Contact not found.", "not_found")
        if contact.archived:
            raise _invalid("contact_id", "The contact is archived.")
        customer_id = body.customer_id or contact.customer_id
        if body.customer_id is not None:
            customer = await crm.get_customer(self.db, self.tenant, body.customer_id)
            if customer is None:
                raise _invalid("customer_id", "Customer not found.", "not_found")
            if customer.archived:
                raise _invalid("customer_id", "The customer is archived.")
        if body.lead_id is not None:
            await self._check_lead(body.lead_id, contact.id)
        price_list = await catalogue.get_price_list(self.db, self.tenant, body.price_list_id)
        if price_list is None:
            raise _invalid(
                "price_list_id",
                "Price list not found."
                if body.price_list_id
                else "There is no default price list.",
                "not_found",
            )
        settings = await self.settings()
        quote = Quote(
            organization_id=self.org,
            number=await self._next_number(settings.number_prefix),
            title=body.title,
            contact_id=contact.id,
            customer_id=customer_id,
            lead_id=body.lead_id,
            price_list_id=price_list.id,
            status=QuoteStatus.DRAFT,
            current_version=1,
            created_by_user_id=self.actor,
        )
        self.db.add(quote)
        await self.db.flush()
        self.db.add(
            Version(
                organization_id=self.org,
                quote_id=quote.id,
                version=1,
                status=VersionStatus.DRAFT,
                prices_include_vat=price_list.prices_include_vat,
                created_by_user_id=self.actor,
            )
        )
        await self.db.flush()
        await self._audit(
            "quote.created",
            quote.id,
            {"number": quote.number, "price_list_id": str(price_list.id)},
        )
        return quote.id

    async def _check_lead(self, lead_id: uuid.UUID, contact_id: uuid.UUID) -> None:
        lead = await crm.get_lead(self.db, self.tenant, lead_id)
        if lead is None:
            raise _invalid("lead_id", "Lead not found.", "not_found")
        if lead.archived:
            raise _invalid("lead_id", "The lead is archived.")
        if lead.contact_id != contact_id:
            raise _invalid("lead_id", "The lead belongs to a different contact.")

    async def update_quote(self, quote_id: uuid.UUID, body: schemas.QuoteUpdate) -> None:
        quote, version = await self._draft(quote_id)
        values = body.model_dump(exclude_unset=True)
        changed: list[str] = []
        if values.get("title") and values["title"] != quote.title:
            quote.title = values["title"]
            changed.append("title")
        if "lead_id" in values and values["lead_id"] != quote.lead_id:
            if values["lead_id"] is not None:
                await self._check_lead(values["lead_id"], quote.contact_id)
            quote.lead_id = values["lead_id"]
            changed.append("lead_id")
        if "notes" in values and values["notes"] != version.notes:
            version.notes = values["notes"]
            changed.append("notes")
        if changed:
            quote.updated_at = datetime.now(UTC)
            await self.db.flush()
            await self._audit("quote.updated", quote.id, {"fields": changed})

    # --- lines -----------------------------------------------------------------------------

    def _check_discount(self, discount: Decimal, limit: Decimal) -> None:
        if discount > limit and not self._can_approve():
            raise _invalid(
                "discount_percent",
                f"Discounts above {limit}% need an approver.",
                "above_limit",
            )

    async def _next_position(self, version: Version) -> int:
        current = await self.db.scalar(
            select(func.max(Line.position)).where(
                Line.organization_id == self.org, Line.version_id == version.id
            )
        )
        return int(current or 0) + 1

    async def _touch(self, quote: Quote) -> None:
        quote.updated_at = datetime.now(UTC)
        await self.db.flush()

    async def _sku(self, quote: Quote, variant_id: uuid.UUID) -> catalogue.SkuInfo:
        sku = (
            await catalogue.get_skus(self.db, self.tenant, [variant_id], quote.price_list_id)
        ).get(variant_id)
        if sku is None:
            raise _invalid("variant_id", "SKU not found.", "not_found")
        if sku.archived:
            raise _invalid("variant_id", "This SKU is archived.")
        if sku.price is None:
            raise _invalid("variant_id", "This SKU has no price on the quote's price list.")
        if sku.vat is None or sku.vat.archived:
            raise _invalid("variant_id", "This product has no active VAT rate.")
        return sku

    def _snapshot(self, line: Line, sku: catalogue.SkuInfo) -> None:
        # Both checked in _sku.
        assert sku.price is not None  # noqa: S101
        assert sku.vat is not None  # noqa: S101
        line.sku = sku.sku
        line.description = sku.description[:300]
        line.unit_price_minor = sku.price.amount_minor
        line.source_price_id = sku.price.id
        line.price_valid_from = sku.price.valid_from
        line.vat_rate_id = sku.vat.id
        line.vat_code = sku.vat.code
        line.vat_percent = sku.vat.rate_percent

    async def add_line(
        self, quote_id: uuid.UUID, body: schemas.CatalogueLineCreate | schemas.CustomLineCreate
    ) -> None:
        quote, version = await self._draft(quote_id)
        self._check_discount(body.discount_percent, (await self.settings()).max_discount_percent)
        line = Line(
            organization_id=self.org,
            version_id=version.id,
            position=await self._next_position(version),
            quantity=body.quantity,
            discount_percent=body.discount_percent,
        )
        if isinstance(body, schemas.CatalogueLineCreate):
            variant_id = body.variant_id
            if variant_id is None and body.sku:
                variant_id = await catalogue.find_variant_id(self.db, self.tenant, body.sku)
                if variant_id is None:
                    raise _invalid("sku", "SKU not found.", "not_found")
            if variant_id is None:
                raise _invalid("variant_id", "Choose a SKU.", "missing")
            line.kind = LineKind.CATALOGUE
            line.variant_id = variant_id
            self._snapshot(line, await self._sku(quote, variant_id))
        else:
            vat = await catalogue.get_vat_rate(self.db, self.tenant, body.vat_rate_id)
            if vat is None:
                raise _invalid("vat_rate_id", "VAT rate not found.", "not_found")
            if vat.archived:
                raise _invalid("vat_rate_id", "This VAT rate is archived.")
            line.kind = LineKind.CUSTOM
            line.description = body.description
            line.unit_price_minor = parse_amount(body.unit_price)
            line.vat_rate_id, line.vat_code, line.vat_percent = vat.id, vat.code, vat.rate_percent
        _apply_totals(line, version.prices_include_vat)
        self.db.add(line)
        await self._touch(quote)
        await self._audit(
            "line.added",
            quote.id,
            {"line_id": str(line.id), "kind": line.kind.value, "sku": line.sku},
        )

    async def update_line(
        self, quote_id: uuid.UUID, line_id: uuid.UUID, body: schemas.LineUpdate
    ) -> None:
        quote, version = await self._draft(quote_id)
        line = await self._line(version, line_id)
        values = body.model_dump(exclude_unset=True, exclude_none=True)
        if line.kind is LineKind.CATALOGUE and ({"description", "unit_price"} & values.keys()):
            raise _invalid(
                "unit_price", "Catalogue lines take their price and description from the catalogue."
            )
        if "discount_percent" in values:
            self._check_discount(
                values["discount_percent"], (await self.settings()).max_discount_percent
            )
            line.discount_percent = values["discount_percent"]
        if "quantity" in values:
            line.quantity = values["quantity"]
        if "description" in values:
            line.description = values["description"]
        if "unit_price" in values:
            line.unit_price_minor = parse_amount(values["unit_price"])
        _apply_totals(line, version.prices_include_vat)
        await self._touch(quote)
        await self._audit(
            "line.updated", quote.id, {"line_id": str(line.id), "fields": sorted(values)}
        )

    async def refresh_line(self, quote_id: uuid.UUID, line_id: uuid.UUID) -> None:
        """Take the catalogue's current price, VAT rate and description for a SKU line."""
        quote, version = await self._draft(quote_id)
        line = await self._line(version, line_id)
        if line.kind is not LineKind.CATALOGUE or line.variant_id is None:
            raise StateError("Only catalogue lines can be refreshed.")
        before = line.unit_price_minor
        self._snapshot(line, await self._sku(quote, line.variant_id))
        _apply_totals(line, version.prices_include_vat)
        await self._touch(quote)
        await self._audit(
            "line.refreshed",
            quote.id,
            {"line_id": str(line.id), "from_minor": before, "to_minor": line.unit_price_minor},
        )

    async def delete_line(self, quote_id: uuid.UUID, line_id: uuid.UUID) -> None:
        quote, version = await self._draft(quote_id)
        line = await self._line(version, line_id)
        await self.db.delete(line)
        await self._touch(quote)
        await self._audit("line.removed", quote.id, {"line_id": str(line_id), "sku": line.sku})

    # --- lifecycle -------------------------------------------------------------------------

    async def approve(self, quote_id: uuid.UUID, body: schemas.ApproveRequest) -> None:
        quote = await self._quote(quote_id, lock=True)
        if not can(quote.status, "approve"):
            raise StateError("Only a draft quote can be approved.")
        if body.version != quote.current_version:
            raise StateError("This quote changed since you opened it. Reload and review it again.")
        version = await self._version(quote)
        lines = await self._lines(version)
        if not lines:
            raise StateError("Add at least one line before approving.")
        found = await self.warnings(quote, lines)
        blocking = [w for w in found if w.blocking]
        if blocking:
            raise ApprovalBlockedError(
                "Fix the highlighted lines before approving: refresh the price or remove them.",
                details=[
                    ErrorDetail(loc=["lines", str(w.line_id)], msg=w.message, type=w.code.value)
                    for w in blocking
                ],
            )
        acknowledged = {(a.line_id, a.code) for a in body.acknowledge}
        missing = [w for w in found if (w.line_id, w.code) not in acknowledged]
        if missing:
            raise ApprovalBlockedError(
                "Confirm the stock warnings before approving.",
                details=[
                    ErrorDetail(loc=["body", "acknowledge"], msg=w.message, type=w.code.value)
                    for w in missing
                ],
            )
        totals = quote_totals(
            (_input(x) for x in lines), prices_include_vat=version.prices_include_vat
        )
        settings = await self.settings()
        version.status = VersionStatus.APPROVED
        version.list_minor = totals.list_minor
        version.discount_minor = totals.discount_minor
        version.net_minor = totals.net_minor
        version.vat_minor = totals.vat_minor
        version.gross_minor = totals.gross_minor
        version.vat_breakdown = [
            {
                "code": g.code,
                "rate_percent": str(g.rate_percent),
                "net_minor": g.net_minor,
                "vat_minor": g.vat_minor,
            }
            for g in totals.vat_breakdown
        ]
        version.acknowledged_warnings = [
            {"line_id": str(w.line_id), "code": w.code.value, "message": w.message} for w in found
        ]
        version.valid_until = self._today() + timedelta(days=settings.validity_days)
        version.approved_by_user_id = self.actor
        version.approved_at = datetime.now(UTC)
        quote.status = QuoteStatus.APPROVED
        quote.status_changed_at = datetime.now(UTC)
        await self._touch(quote)
        over_limit = [x for x in lines if x.discount_percent > settings.max_discount_percent]
        await self._audit(
            "quote.approved",
            quote.id,
            {
                "version": version.version,
                "gross_minor": totals.gross_minor,
                "acknowledged": [w.code.value for w in found],
                "discounts_above_limit": len(over_limit),
            },
        )

    async def revise(self, quote_id: uuid.UUID) -> None:
        quote = await self._quote(quote_id, lock=True)
        if not can(quote.status, "revise"):
            raise StateError("Only an approved quote can be revised.")
        old = await self._version(quote)
        lines = await self._lines(old)
        old.status = VersionStatus.SUPERSEDED
        await self.db.flush()
        new = Version(
            organization_id=self.org,
            quote_id=quote.id,
            version=old.version + 1,
            status=VersionStatus.DRAFT,
            prices_include_vat=old.prices_include_vat,
            notes=old.notes,
            created_by_user_id=self.actor,
        )
        self.db.add(new)
        await self.db.flush()
        for line in lines:
            self.db.add(
                Line(
                    organization_id=self.org,
                    version_id=new.id,
                    position=line.position,
                    kind=line.kind,
                    variant_id=line.variant_id,
                    sku=line.sku,
                    description=line.description,
                    quantity=line.quantity,
                    unit_price_minor=line.unit_price_minor,
                    source_price_id=line.source_price_id,
                    price_valid_from=line.price_valid_from,
                    vat_rate_id=line.vat_rate_id,
                    vat_code=line.vat_code,
                    vat_percent=line.vat_percent,
                    discount_percent=line.discount_percent,
                    net_minor=line.net_minor,
                    vat_minor=line.vat_minor,
                    gross_minor=line.gross_minor,
                )
            )
        quote.current_version = new.version
        quote.status = QuoteStatus.DRAFT
        quote.status_changed_at = datetime.now(UTC)
        await self._touch(quote)
        await self._audit(
            "quote.revised", quote.id, {"from_version": old.version, "to_version": new.version}
        )

    async def record_outcome(self, quote_id: uuid.UUID, body: schemas.OutcomeRequest) -> None:
        quote = await self._quote(quote_id, lock=True)
        target = QuoteStatus.ACCEPTED if body.outcome == "accepted" else QuoteStatus.DECLINED
        if not can(quote.status, "accept" if target is QuoteStatus.ACCEPTED else "decline"):
            raise StateError("Only an approved quote can be accepted or declined.")
        version = await self._version(quote)
        if (
            target is QuoteStatus.ACCEPTED
            and version.valid_until
            and version.valid_until < self._today()
        ):
            raise StateError("This quote expired. Revise it to confirm prices and stock first.")
        quote.status = target
        quote.outcome_reason = body.reason
        quote.status_changed_at = datetime.now(UTC)
        await self._touch(quote)
        await self._audit(f"quote.{target.value}", quote.id, {"version": version.version})

    async def cancel(self, quote_id: uuid.UUID, body: schemas.CancelRequest) -> None:
        quote = await self._quote(quote_id, lock=True)
        if not can(quote.status, "cancel"):
            raise StateError("This quote can no longer be cancelled.")
        quote.status = QuoteStatus.CANCELLED
        quote.outcome_reason = body.reason
        quote.status_changed_at = datetime.now(UTC)
        await self._touch(quote)
        await self._audit("quote.cancelled", quote.id, {"version": quote.current_version})
