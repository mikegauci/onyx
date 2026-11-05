"""Catalogue domain service: the only code that changes catalogue rows.

Every method runs inside the request transaction, bound to the caller's workspace. The tenant
comes from ``WorkspaceAccess`` (never from input); queries add an explicit ``organization_id``
filter on top of row-level security. Changes write their audit entry in the same transaction.

Read model rules (PR-010): a value is shown only with its source and timestamps, and missing
data stays missing. No price row means "price not provided" for that list; no stock row means
availability "unknown"; no VAT rate means the product has no VAT set. Nothing is defaulted.
"""

import hashlib
import uuid
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, or_, select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit.record import record_workspace_audit
from app.core.auth.deps import WorkspaceAccess
from app.core.errors import ConflictError, ErrorDetail, NotFoundError, ValidationFailedError
from app.modules.catalogue import schemas
from app.modules.catalogue.importer import (
    DEFAULT_LOCATION,
    FUTURE_TOLERANCE,
    CatalogueRow,
    FieldError,
    ImportFileError,
    RowError,
    format_minor,
    normalise_code,
    parse_catalogue_csv,
    product_details,
)
from app.modules.catalogue.models import (
    ImportRun,
    ImportSourceKind,
    Price,
    PriceList,
    Product,
    StockLevel,
    Variant,
    VatRate,
)
from app.modules.crm.pagination import encode_cursor, paginate

UNIQUE_CODE_CONSTRAINTS = {
    "uq_catalogue_vat_rates_organization_id_code": "code",
    "uq_catalogue_price_lists_organization_id_code": "code",
    "uq_catalogue_price_lists_one_default": "is_default",
}
IMPORT_RACE_CONSTRAINTS = {
    "uq_catalogue_products_organization_id_code",
    "uq_catalogue_variants_organization_id_sku",
}


class DuplicateCodeError(ConflictError):
    default_message = "This code is already used in this workspace."


class ImportConflictError(ConflictError):
    default_message = "The catalogue changed while importing. Run the import again."


def _like(term: str) -> str:
    escaped = term.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _page[T](rows: list[T], limit: int, key: Any) -> tuple[list[T], str | None]:
    page = rows[:limit]
    if len(rows) <= limit:
        return page, None
    when, item_id = key(page[-1])
    return page, encode_cursor(when, item_id)


def _invalid(field: str, message: str) -> ValidationFailedError:
    return ValidationFailedError(
        message, details=[ErrorDetail(loc=["body", field], msg=message, type="invalid")]
    )


def vat_rate_out(rate: VatRate) -> schemas.VatRateOut:
    return schemas.VatRateOut(
        id=rate.id,
        code=rate.code,
        name=rate.name,
        rate_percent=rate.rate_percent,
        archived_at=rate.archived_at,
        created_at=rate.created_at,
    )


def price_list_out(price_list: PriceList) -> schemas.PriceListOut:
    return schemas.PriceListOut(
        id=price_list.id,
        code=price_list.code,
        name=price_list.name,
        currency="EUR",
        prices_include_vat=price_list.prices_include_vat,
        is_default=price_list.is_default,
        created_at=price_list.created_at,
    )


def import_run_out(run: ImportRun) -> schemas.ImportRunOut:
    return schemas.ImportRunOut(
        id=run.id,
        source_kind=run.source_kind.value,
        filename=run.filename,
        file_sha256=run.file_sha256,
        price_list_id=run.price_list_id,
        source_exported_at=run.source_exported_at,
        counts=run.counts,
        created_by_user_id=run.created_by_user_id,
        created_at=run.created_at,
    )


@dataclass
class _ImportPlan:
    """What an import would change, computed before anything is written."""

    rows: list[CatalogueRow]
    errors: list[RowError]
    counts: schemas.ImportCounts
    new_products: dict[str, dict[str, Any]]
    product_updates: dict[uuid.UUID, dict[str, Any]]
    new_variants: list[CatalogueRow]
    variant_updates: dict[uuid.UUID, dict[str, Any]]
    prices: list[CatalogueRow]
    stock: list[CatalogueRow]


class CatalogueService:
    def __init__(self, db: AsyncSession, workspace: WorkspaceAccess) -> None:
        self.db = db
        self.workspace = workspace
        self.org = workspace.tenant.organization_id

    # --- shared ----------------------------------------------------------------------------

    async def _audit(
        self, action: str, target_type: str, target_id: uuid.UUID, details: dict[str, Any]
    ) -> None:
        await record_workspace_audit(
            self.db,
            self.workspace,
            action=f"catalogue.{action}",
            target_type=target_type,
            target_id=target_id,
            details=details,
        )

    async def _flush(self) -> None:
        """Flush, turning a lost race on a unique code into a 409 like the pre-check."""
        try:
            await self.db.flush()
        except IntegrityError as exc:
            constraint = getattr(getattr(exc.orig, "diag", None), "constraint_name", None) or ""
            if constraint in IMPORT_RACE_CONSTRAINTS:
                raise ImportConflictError from exc
            field = UNIQUE_CODE_CONSTRAINTS.get(constraint)
            if field is None:
                raise
            raise DuplicateCodeError(
                details=[ErrorDetail(loc=["body", field], msg="Already used.", type="duplicate")]
            ) from exc

    async def _get[M](self, model: type[M], item_id: uuid.UUID, label: str) -> M:
        item = await self.db.scalar(
            select(model).where(
                model.organization_id == self.org,  # type: ignore[attr-defined]
                model.id == item_id,  # type: ignore[attr-defined]
            )
        )
        if item is None:
            raise NotFoundError(f"{label} not found.")
        return item

    # --- VAT rates -------------------------------------------------------------------------

    async def list_vat_rates(self, *, include_archived: bool) -> list[VatRate]:
        query = select(VatRate).where(VatRate.organization_id == self.org)
        if not include_archived:
            query = query.where(VatRate.archived_at.is_(None))
        return list((await self.db.scalars(query.order_by(VatRate.code))).all())

    async def create_vat_rate(self, body: schemas.VatRateCreate) -> VatRate:
        existing = await self.db.scalar(
            select(VatRate.id).where(VatRate.organization_id == self.org, VatRate.code == body.code)
        )
        if existing is not None:
            raise DuplicateCodeError(
                details=[
                    ErrorDetail(
                        loc=["body", "code"],
                        msg="Already used.",
                        type="duplicate",
                        ref=str(existing),
                    )
                ]
            )
        rate = VatRate(
            organization_id=self.org,
            code=body.code,
            name=body.name,
            rate_percent=body.rate_percent,
            created_by_user_id=self.workspace.user.id,
        )
        self.db.add(rate)
        await self._flush()
        await self._audit(
            "vat_rate.created",
            "catalogue_vat_rate",
            rate.id,
            {"code": rate.code, "rate_percent": str(rate.rate_percent)},
        )
        return rate

    async def update_vat_rate(self, rate_id: uuid.UUID, body: schemas.VatRateUpdate) -> VatRate:
        rate = await self._get(VatRate, rate_id, "VAT rate")
        if rate.name != body.name:
            rate.name = body.name
            await self._flush()
            await self._audit(
                "vat_rate.updated", "catalogue_vat_rate", rate.id, {"fields": ["name"]}
            )
        return rate

    async def set_vat_rate_archived(self, rate_id: uuid.UUID, archived: bool) -> VatRate:
        rate = await self._get(VatRate, rate_id, "VAT rate")
        if (rate.archived_at is not None) != archived:
            rate.archived_at = datetime.now(UTC) if archived else None
            await self._flush()
            action = "vat_rate.archived" if archived else "vat_rate.restored"
            await self._audit(action, "catalogue_vat_rate", rate.id, {})
        return rate

    # --- price lists -----------------------------------------------------------------------

    async def list_price_lists(self) -> list[PriceList]:
        query = (
            select(PriceList)
            .where(PriceList.organization_id == self.org)
            .order_by(PriceList.is_default.desc(), PriceList.code)
        )
        return list((await self.db.scalars(query)).all())

    async def _clear_default(self) -> None:
        await self.db.execute(
            update(PriceList)
            .where(PriceList.organization_id == self.org, PriceList.is_default.is_(True))
            .values(is_default=False)
        )

    async def create_price_list(self, body: schemas.PriceListCreate) -> PriceList:
        existing = await self.db.scalar(
            select(PriceList.id).where(
                PriceList.organization_id == self.org, PriceList.code == body.code
            )
        )
        if existing is not None:
            raise DuplicateCodeError(
                details=[
                    ErrorDetail(
                        loc=["body", "code"],
                        msg="Already used.",
                        type="duplicate",
                        ref=str(existing),
                    )
                ]
            )
        has_default = await self.db.scalar(
            select(PriceList.id).where(
                PriceList.organization_id == self.org, PriceList.is_default.is_(True)
            )
        )
        # The first list is the default, so imports always have somewhere to put prices.
        is_default = body.is_default or has_default is None
        if is_default and has_default is not None:
            await self._clear_default()
        price_list = PriceList(
            organization_id=self.org,
            code=body.code,
            name=body.name,
            prices_include_vat=body.prices_include_vat,
            is_default=is_default,
            created_by_user_id=self.workspace.user.id,
        )
        self.db.add(price_list)
        await self._flush()
        await self._audit(
            "price_list.created",
            "catalogue_price_list",
            price_list.id,
            {
                "code": price_list.code,
                "prices_include_vat": price_list.prices_include_vat,
                "is_default": is_default,
            },
        )
        return price_list

    async def update_price_list(
        self, price_list_id: uuid.UUID, body: schemas.PriceListUpdate
    ) -> PriceList:
        price_list = await self._get(PriceList, price_list_id, "Price list")
        fields: list[str] = []
        if body.name is not None and body.name != price_list.name:
            price_list.name = body.name
            fields.append("name")
        if body.is_default and not price_list.is_default:
            await self._clear_default()
            price_list.is_default = True
            fields.append("is_default")
        if fields:
            await self._flush()
            await self.db.refresh(price_list)
            await self._audit(
                "price_list.updated", "catalogue_price_list", price_list.id, {"fields": fields}
            )
        return price_list

    # --- read model ------------------------------------------------------------------------

    async def _vat_by_id(self) -> dict[uuid.UUID, VatRate]:
        rows = await self.db.scalars(select(VatRate).where(VatRate.organization_id == self.org))
        return {rate.id: rate for rate in rows}

    def _variant_count(self) -> Any:
        return (
            select(func.count(Variant.id))
            .where(
                Variant.organization_id == Product.organization_id,
                Variant.product_id == Product.id,
                Variant.archived_at.is_(None),
            )
            .scalar_subquery()
        )

    @staticmethod
    def _summary(
        product: Product, variant_count: int, vat: dict[uuid.UUID, VatRate]
    ) -> schemas.ProductSummary:
        rate = vat.get(product.vat_rate_id) if product.vat_rate_id else None
        return schemas.ProductSummary(
            id=product.id,
            code=product.code,
            name=product.name,
            brand=product.brand,
            category=product.category,
            vat=(
                schemas.VatOut(
                    id=rate.id, code=rate.code, name=rate.name, rate_percent=rate.rate_percent
                )
                if rate
                else None
            ),
            variant_count=variant_count,
            archived_at=product.archived_at,
            updated_at=product.updated_at,
        )

    async def list_products(
        self,
        *,
        q: str | None,
        category: str | None,
        include_archived: bool,
        limit: int,
        cursor: str | None,
    ) -> tuple[list[schemas.ProductSummary], str | None]:
        query = select(Product, self._variant_count()).where(Product.organization_id == self.org)
        if not include_archived:
            query = query.where(Product.archived_at.is_(None))
        if category:
            query = query.where(func.lower(Product.category) == category.strip().lower())
        if q:
            pattern = _like(q)
            sku_match = (
                select(Variant.id)
                .where(
                    Variant.organization_id == Product.organization_id,
                    Variant.product_id == Product.id,
                    Variant.sku.ilike(pattern, escape="\\"),
                )
                .exists()
            )
            query = query.where(
                or_(
                    Product.name.ilike(pattern, escape="\\"),
                    Product.code.ilike(pattern, escape="\\"),
                    Product.brand.ilike(pattern, escape="\\"),
                    sku_match,
                )
            )
        query = paginate(query, Product.created_at, Product.id, limit=limit, cursor=cursor)
        rows = list((await self.db.execute(query)).tuples().all())
        page, next_cursor = _page(rows, limit, lambda r: (r[0].created_at, r[0].id))
        vat = await self._vat_by_id()
        return [self._summary(p, count, vat) for p, count in page], next_cursor

    async def _sources(self, ids: Iterable[uuid.UUID | None]) -> dict[uuid.UUID, ImportRun]:
        wanted = {i for i in ids if i is not None}
        if not wanted:
            return {}
        rows = await self.db.scalars(
            select(ImportRun).where(ImportRun.organization_id == self.org, ImportRun.id.in_(wanted))
        )
        return {run.id: run for run in rows}

    @staticmethod
    def _source(run_id: uuid.UUID | None, runs: dict[uuid.UUID, ImportRun]) -> schemas.SourceOut:
        run = runs.get(run_id) if run_id else None
        return schemas.SourceOut(
            import_run_id=run_id,
            filename=run.filename if run else None,
            source_exported_at=run.source_exported_at if run else None,
        )

    async def current_prices(
        self, variant_ids: Sequence[uuid.UUID], price_list_id: uuid.UUID | None = None
    ) -> list[Price]:
        """The latest price per (variant, list). Future-dated prices cannot be imported."""
        if not variant_ids:
            return []
        query = select(Price).where(
            Price.organization_id == self.org, Price.variant_id.in_(variant_ids)
        )
        if price_list_id is not None:
            query = query.where(Price.price_list_id == price_list_id)
        query = query.distinct(Price.variant_id, Price.price_list_id).order_by(
            Price.variant_id,
            Price.price_list_id,
            Price.valid_from.desc(),
            Price.recorded_at.desc(),
            Price.id.desc(),
        )
        return list((await self.db.scalars(query)).all())

    async def current_stock(self, variant_ids: Sequence[uuid.UUID]) -> list[StockLevel]:
        """The latest observation per (variant, location)."""
        if not variant_ids:
            return []
        query = (
            select(StockLevel)
            .where(StockLevel.organization_id == self.org, StockLevel.variant_id.in_(variant_ids))
            .distinct(StockLevel.variant_id, StockLevel.location)
            .order_by(
                StockLevel.variant_id,
                StockLevel.location,
                StockLevel.observed_at.desc(),
                StockLevel.recorded_at.desc(),
                StockLevel.id.desc(),
            )
        )
        return list((await self.db.scalars(query)).all())

    async def _variants_out(self, variants: Sequence[Variant]) -> list[schemas.VariantOut]:
        ids = [v.id for v in variants]
        prices = await self.current_prices(ids)
        stock = await self.current_stock(ids)
        lists = {pl.id: pl for pl in await self.list_price_lists()}
        runs = await self._sources(
            [p.import_run_id for p in prices] + [s.import_run_id for s in stock]
        )
        prices_by: dict[uuid.UUID, list[schemas.PriceOut]] = {}
        for price in prices:
            price_list = lists[price.price_list_id]
            prices_by.setdefault(price.variant_id, []).append(
                schemas.PriceOut(
                    price_list_id=price_list.id,
                    price_list_code=price_list.code,
                    currency="EUR",
                    amount=format_minor(price.amount_minor),
                    amount_minor=price.amount_minor,
                    includes_vat=price_list.prices_include_vat,
                    valid_from=price.valid_from,
                    recorded_at=price.recorded_at,
                    source=self._source(price.import_run_id, runs),
                )
            )
        stock_by: dict[uuid.UUID, list[schemas.StockOut]] = {}
        for level in stock:
            stock_by.setdefault(level.variant_id, []).append(
                schemas.StockOut(
                    location=level.location,
                    quantity_available=level.quantity_available,
                    observed_at=level.observed_at,
                    recorded_at=level.recorded_at,
                    source=self._source(level.import_run_id, runs),
                )
            )
        out = []
        for variant in variants:
            levels = stock_by.get(variant.id, [])
            if not levels:
                availability: schemas.Availability = "unknown"
            elif any(level.quantity_available > 0 for level in levels):
                availability = "in_stock"
            else:
                availability = "out_of_stock"
            out.append(
                schemas.VariantOut(
                    id=variant.id,
                    product_id=variant.product_id,
                    sku=variant.sku,
                    name=variant.name,
                    attributes=variant.attributes,
                    prices=prices_by.get(variant.id, []),
                    stock=levels,
                    availability=availability,
                    archived_at=variant.archived_at,
                    updated_at=variant.updated_at,
                )
            )
        return out

    async def product_detail(self, product_id: uuid.UUID) -> schemas.ProductDetail:
        product = await self._get(Product, product_id, "Product")
        variants = list(
            (
                await self.db.scalars(
                    select(Variant)
                    .where(Variant.organization_id == self.org, Variant.product_id == product.id)
                    .order_by(Variant.sku)
                )
            ).all()
        )
        vat = await self._vat_by_id()
        active = sum(1 for v in variants if v.archived_at is None)
        summary = self._summary(product, active, vat)
        runs = await self._sources([product.last_import_id])
        return schemas.ProductDetail(
            **summary.model_dump(),
            description=product.description,
            last_import=(
                self._source(product.last_import_id, runs) if product.last_import_id else None
            ),
            price_lists=[price_list_out(pl) for pl in await self.list_price_lists()],
            variants=await self._variants_out(variants),
        )

    async def lookup_sku(self, sku: str) -> schemas.VariantLookup:
        try:
            code = normalise_code(sku)
        except FieldError as exc:
            raise NotFoundError("SKU not found.") from exc
        variant = await self.db.scalar(
            select(Variant).where(Variant.organization_id == self.org, Variant.sku == code)
        )
        if variant is None:
            raise NotFoundError("SKU not found.")
        product = await self._get(Product, variant.product_id, "Product")
        count = await self.db.scalar(
            select(func.count(Variant.id)).where(
                Variant.organization_id == self.org,
                Variant.product_id == product.id,
                Variant.archived_at.is_(None),
            )
        )
        (out,) = await self._variants_out([variant])
        return schemas.VariantLookup(
            variant=out, product=self._summary(product, count or 0, await self._vat_by_id())
        )

    async def set_product_archived(self, product_id: uuid.UUID, archived: bool) -> None:
        product = await self._get(Product, product_id, "Product")
        if (product.archived_at is not None) != archived:
            product.archived_at = datetime.now(UTC) if archived else None
            await self._flush()
            action = "product.archived" if archived else "product.restored"
            await self._audit(action, "catalogue_product", product.id, {})

    async def set_variant_archived(self, variant_id: uuid.UUID, archived: bool) -> Variant:
        variant = await self._get(Variant, variant_id, "Variant")
        if (variant.archived_at is not None) != archived:
            variant.archived_at = datetime.now(UTC) if archived else None
            await self._flush()
            action = "variant.archived" if archived else "variant.restored"
            await self._audit(action, "catalogue_variant", variant.id, {"sku": variant.sku})
        return variant

    async def variant_out(self, variant: Variant) -> schemas.VariantOut:
        (out,) = await self._variants_out([variant])
        return out

    async def list_import_runs(
        self, *, limit: int, cursor: str | None
    ) -> tuple[list[ImportRun], str | None]:
        query = paginate(
            select(ImportRun).where(ImportRun.organization_id == self.org),
            ImportRun.created_at,
            ImportRun.id,
            limit=limit,
            cursor=cursor,
        )
        rows = list((await self.db.scalars(query)).all())
        return _page(rows, limit, lambda r: (r.created_at, r.id))

    # --- import ----------------------------------------------------------------------------

    async def _import_price_list(
        self, price_list_id: uuid.UUID | None, *, needed: bool
    ) -> PriceList | None:
        if price_list_id is not None:
            price_list = await self.db.scalar(
                select(PriceList).where(
                    PriceList.organization_id == self.org, PriceList.id == price_list_id
                )
            )
            if price_list is None:
                raise _invalid("price_list_id", "Price list not found.")
            return price_list
        price_list = await self.db.scalar(
            select(PriceList).where(
                PriceList.organization_id == self.org, PriceList.is_default.is_(True)
            )
        )
        if price_list is None and needed:
            raise _invalid(
                "price_list_id", "The file has prices but there is no price list. Create one first."
            )
        return price_list

    async def import_catalogue(
        self, body: schemas.CatalogueImportRequest
    ) -> schemas.CatalogueImportResult:
        now = datetime.now(UTC)
        exported = body.source_exported_at.astimezone(UTC) if body.source_exported_at else None
        if exported is not None and exported > now + FUTURE_TOLERANCE:
            raise _invalid("source_exported_at", "The export time is in the future.")
        try:
            parsed = parse_catalogue_csv(body.csv, now=now, source_exported_at=exported)
        except ImportFileError as exc:
            raise ValidationFailedError(
                str(exc),
                details=[ErrorDetail(loc=["body", "csv"], msg=str(exc), type="invalid_file")],
            ) from exc
        price_list = await self._import_price_list(
            body.price_list_id, needed=any(r.price_minor is not None for r in parsed.rows)
        )
        if not body.dry_run:
            # One import per workspace at a time, so plans are computed on settled data.
            await self.db.execute(
                text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
                {"key": f"catalogue-import:{self.org}"},
            )

        sha256 = hashlib.sha256(body.csv.encode("utf-8")).hexdigest()
        previous = await self.db.scalar(
            select(ImportRun)
            .where(
                ImportRun.organization_id == self.org,
                ImportRun.file_sha256 == sha256,
                ImportRun.price_list_id.is_not_distinct_from(price_list.id if price_list else None),
            )
            .order_by(ImportRun.created_at.desc())
            .limit(1)
        )
        if previous is not None:
            return schemas.CatalogueImportResult(
                dry_run=body.dry_run,
                total=parsed.total,
                counts=schemas.ImportCounts.model_validate(previous.counts),
                errors=[],
                import_run_id=previous.id,
                already_imported=True,
            )

        plan = await self._plan(parsed.rows, list(parsed.errors), price_list, exported or now)
        plan.counts.rows = parsed.total
        plan.counts.errors = len(plan.errors)
        run_id = None
        if not body.dry_run and plan.rows:
            run_id = await self._apply(plan, body, sha256, price_list, exported, now)
        return schemas.CatalogueImportResult(
            dry_run=body.dry_run,
            total=parsed.total,
            counts=plan.counts,
            errors=[
                schemas.ImportRowError(row=e.row, field=e.field, message=e.message)
                for e in sorted(plan.errors, key=lambda e: (e.row, e.field))
            ],
            import_run_id=run_id,
        )

    async def _plan(
        self,
        rows: list[CatalogueRow],
        errors: list[RowError],
        price_list: PriceList | None,
        valid_from: datetime,
    ) -> _ImportPlan:
        vat_codes = {r.vat_code for r in rows if r.vat_code}
        vat: dict[str, uuid.UUID] = {}
        if vat_codes:
            found = await self.db.execute(
                select(VatRate.code, VatRate.id).where(
                    VatRate.organization_id == self.org,
                    VatRate.code.in_(vat_codes),
                    VatRate.archived_at.is_(None),
                )
            )
            vat = dict(found.tuples())
        products = {
            p.code: p
            for p in await self.db.scalars(
                select(Product).where(
                    Product.organization_id == self.org,
                    Product.code.in_({r.product_code for r in rows}),
                )
            )
        }
        product_codes = {p.id: p.code for p in products.values()}
        variants = {
            v.sku: v
            for v in await self.db.scalars(
                select(Variant).where(
                    Variant.organization_id == self.org, Variant.sku.in_({r.sku for r in rows})
                )
            )
        }

        kept: list[CatalogueRow] = []
        for row in rows:
            if row.vat_code and row.vat_code not in vat:
                errors.append(RowError(row.row, "vat_code", "Unknown or archived VAT code."))
                continue
            existing = variants.get(row.sku)
            if existing is not None and product_codes.get(existing.product_id) != row.product_code:
                errors.append(
                    RowError(row.row, "sku", "This SKU already belongs to another product.")
                )
                continue
            kept.append(row)

        counts = schemas.ImportCounts()
        new_products: dict[str, dict[str, Any]] = {}
        product_updates: dict[uuid.UUID, dict[str, Any]] = {}
        for code, details in product_details(kept).items():
            vat_code = details["vat_code"]
            values: dict[str, Any] = {
                "name": details["product_name"],
                "brand": details["brand"],
                "category": details["category"],
                "description": details["description"],
                "vat_rate_id": vat[vat_code] if vat_code else None,
            }
            product = products.get(code)
            if product is None:
                new_products[code] = values
                counts.products_created += 1
                continue
            # Blank cells are "not provided": they never clear stored values.
            changes = {
                k: v for k, v in values.items() if v is not None and getattr(product, k) != v
            }
            if changes:
                product_updates[product.id] = changes
                counts.products_updated += 1

        new_variants: list[CatalogueRow] = []
        variant_updates: dict[uuid.UUID, dict[str, Any]] = {}
        for row in kept:
            variant = variants.get(row.sku)
            if variant is None:
                new_variants.append(row)
                counts.variants_created += 1
                continue
            variant_changes: dict[str, Any] = {}
            if row.variant_name is not None and row.variant_name != variant.name:
                variant_changes["name"] = row.variant_name
            merged = {**variant.attributes, **row.attributes}
            if merged != variant.attributes:
                variant_changes["attributes"] = merged
            if variant_changes:
                variant_updates[variant.id] = variant_changes
                counts.variants_updated += 1

        known_ids = [v.id for v in variants.values()]
        current_price: dict[uuid.UUID, Price] = {}
        if price_list is not None:
            current_price = {
                p.variant_id: p for p in await self.current_prices(known_ids, price_list.id)
            }
        current_stock = {(s.variant_id, s.location): s for s in await self.current_stock(known_ids)}

        prices: list[CatalogueRow] = []
        stock: list[CatalogueRow] = []
        for row in kept:
            variant = variants.get(row.sku)
            if row.price_minor is not None:
                price = current_price.get(variant.id) if variant else None
                if price is None:
                    prices.append(row)
                elif valid_from < price.valid_from:
                    counts.prices_older_ignored += 1
                elif price.amount_minor == row.price_minor:
                    counts.prices_unchanged += 1
                else:
                    prices.append(row)
            if row.stock_available is not None and row.stock_observed_at is not None:
                level = (
                    current_stock.get((variant.id, row.stock_location or "")) if variant else None
                )
                if level is None:
                    stock.append(row)
                elif row.stock_observed_at < level.observed_at:
                    counts.stock_older_ignored += 1
                elif (
                    row.stock_observed_at == level.observed_at
                    and row.stock_available == level.quantity_available
                ):
                    counts.stock_unchanged += 1
                else:
                    stock.append(row)
        counts.prices_recorded = len(prices)
        counts.stock_recorded = len(stock)
        return _ImportPlan(
            rows=kept,
            errors=errors,
            counts=counts,
            new_products=new_products,
            product_updates=product_updates,
            new_variants=new_variants,
            variant_updates=variant_updates,
            prices=prices,
            stock=stock,
        )

    async def _apply(
        self,
        plan: _ImportPlan,
        body: schemas.CatalogueImportRequest,
        sha256: str,
        price_list: PriceList | None,
        exported: datetime | None,
        now: datetime,
    ) -> uuid.UUID:
        user_id = self.workspace.user.id
        run = ImportRun(
            organization_id=self.org,
            source_kind=ImportSourceKind.CSV,
            filename=body.filename,
            file_sha256=sha256,
            price_list_id=price_list.id if price_list else None,
            source_exported_at=exported,
            counts=plan.counts.model_dump(),
            created_by_user_id=user_id,
        )
        self.db.add(run)
        await self._flush()

        for code, values in plan.new_products.items():
            self.db.add(
                Product(organization_id=self.org, code=code, last_import_id=run.id, **values)
            )
        for product_id, changes in plan.product_updates.items():
            await self.db.execute(
                update(Product)
                .where(Product.organization_id == self.org, Product.id == product_id)
                .values(**changes, last_import_id=run.id, updated_at=func.now())
            )
        await self._flush()

        codes = {r.product_code for r in plan.rows}
        product_ids = dict(
            (
                await self.db.execute(
                    select(Product.code, Product.id).where(
                        Product.organization_id == self.org, Product.code.in_(codes)
                    )
                )
            ).tuples()
        )
        for row in plan.new_variants:
            self.db.add(
                Variant(
                    organization_id=self.org,
                    product_id=product_ids[row.product_code],
                    sku=row.sku,
                    name=row.variant_name,
                    attributes=row.attributes,
                    last_import_id=run.id,
                )
            )
        for variant_id, changes in plan.variant_updates.items():
            await self.db.execute(
                update(Variant)
                .where(Variant.organization_id == self.org, Variant.id == variant_id)
                .values(**changes, last_import_id=run.id, updated_at=func.now())
            )
        await self._flush()

        variant_ids = dict(
            (
                await self.db.execute(
                    select(Variant.sku, Variant.id).where(
                        Variant.organization_id == self.org,
                        Variant.sku.in_({r.sku for r in plan.rows}),
                    )
                )
            ).tuples()
        )
        valid_from = exported or now
        for row in plan.prices:
            if price_list is None or row.price_minor is None:  # excluded by _plan
                continue
            self.db.add(
                Price(
                    organization_id=self.org,
                    variant_id=variant_ids[row.sku],
                    price_list_id=price_list.id,
                    amount_minor=row.price_minor,
                    valid_from=valid_from,
                    import_run_id=run.id,
                    recorded_by_user_id=user_id,
                )
            )
        for row in plan.stock:
            if row.stock_available is None or row.stock_observed_at is None:
                continue  # excluded by _plan
            self.db.add(
                StockLevel(
                    organization_id=self.org,
                    variant_id=variant_ids[row.sku],
                    location=row.stock_location or DEFAULT_LOCATION,
                    quantity_available=row.stock_available,
                    observed_at=row.stock_observed_at,
                    import_run_id=run.id,
                    recorded_by_user_id=user_id,
                )
            )
        await self._flush()
        await self._audit(
            "import.applied",
            "catalogue_import_run",
            run.id,
            {"source_kind": "csv", **plan.counts.model_dump()},
        )
        return run.id
