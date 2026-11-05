"""Request and response models for the catalogue API (the contract behind the TS client).

Amounts are exchanged as decimal strings (``"12.50"``) plus integer cents, never floats.
Missing data is explicit: a variant without a price on a list has no entry for it in
``prices``; a variant without stock data has ``availability = "unknown"`` and no ``stock``.
"""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Any, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StringConstraints, field_validator

from app.modules.catalogue.importer import MAX_BYTES, FieldError, normalise_code

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
Code = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=64)]
Filename = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)]

Availability = Literal["in_stock", "out_of_stock", "unknown"]


class _Input(BaseModel):
    model_config = ConfigDict(extra="forbid")


class _Coded(_Input):
    @field_validator("code", mode="after", check_fields=False)
    @classmethod
    def _code(cls, value: str) -> str:
        try:
            return normalise_code(value)
        except FieldError as exc:
            raise ValueError(str(exc)) from exc


# --- VAT rates -------------------------------------------------------------------------------


class VatRateCreate(_Coded):
    code: Code
    name: Name
    rate_percent: Decimal = Field(ge=0, le=100, max_digits=5, decimal_places=2)

    @field_validator("rate_percent", mode="after")
    @classmethod
    def _two_places(cls, value: Decimal) -> Decimal:
        return value.quantize(Decimal("0.01"))


class VatRateUpdate(_Input):
    name: Name


class VatRateOut(BaseModel):
    id: uuid.UUID
    code: str
    name: str
    rate_percent: Decimal
    archived_at: datetime | None
    created_at: datetime


class VatRateList(BaseModel):
    items: list[VatRateOut]


# --- price lists -----------------------------------------------------------------------------


class PriceListCreate(_Coded):
    code: Code
    name: Name
    prices_include_vat: bool = Field(description="Fixed once created")
    is_default: bool = False


class PriceListUpdate(_Input):
    name: Name | None = None
    is_default: Literal[True] | None = Field(
        default=None, description="Make this the default list (the previous one stops being it)"
    )


class PriceListOut(BaseModel):
    id: uuid.UUID
    code: str
    name: str
    currency: Literal["EUR"]
    prices_include_vat: bool
    is_default: bool
    created_at: datetime


class PriceListList(BaseModel):
    items: list[PriceListOut]


# --- sources ---------------------------------------------------------------------------------


class SourceOut(BaseModel):
    """Where a value came from. ``import_run_id`` is null for values entered another way."""

    import_run_id: uuid.UUID | None
    filename: str | None
    source_exported_at: datetime | None


class PriceOut(BaseModel):
    price_list_id: uuid.UUID
    price_list_code: str
    currency: Literal["EUR"]
    amount: str = Field(description="Decimal string, e.g. '12.50'")
    amount_minor: int = Field(description="Euro cents")
    includes_vat: bool
    valid_from: datetime
    recorded_at: datetime
    source: SourceOut


class StockOut(BaseModel):
    location: str
    quantity_available: int
    observed_at: datetime = Field(description="When the source counted it")
    recorded_at: datetime = Field(description="When Onyx stored it")
    source: SourceOut


class VatOut(BaseModel):
    id: uuid.UUID
    code: str
    name: str
    rate_percent: Decimal


# --- products and variants -------------------------------------------------------------------


class VariantOut(BaseModel):
    id: uuid.UUID
    product_id: uuid.UUID
    sku: str
    name: str | None
    attributes: dict[str, str]
    prices: list[PriceOut] = Field(description="Current price per price list that has one")
    stock: list[StockOut] = Field(description="Latest observation per location")
    availability: Availability
    archived_at: datetime | None
    updated_at: datetime


class ProductSummary(BaseModel):
    id: uuid.UUID
    code: str
    name: str
    brand: str | None
    category: str | None
    vat: VatOut | None = Field(description="Null when no VAT rate is set: not quotable yet")
    variant_count: int
    archived_at: datetime | None
    updated_at: datetime


class ProductPage(BaseModel):
    items: list[ProductSummary]
    next_cursor: str | None


class ProductDetail(ProductSummary):
    description: str | None
    last_import: SourceOut | None
    price_lists: list[PriceListOut] = Field(description="Every list, to show missing prices")
    variants: list[VariantOut]


class VariantLookup(BaseModel):
    """An exact SKU match with its product, for quoting and the assistant."""

    variant: VariantOut
    product: ProductSummary


class ArchiveRequest(_Input):
    archived: bool = True


# --- import ----------------------------------------------------------------------------------


class CatalogueImportRequest(_Input):
    csv: str = Field(max_length=MAX_BYTES, description="The CSV file's text (UTF-8)")
    filename: Filename | None = None
    price_list_id: uuid.UUID | None = Field(
        default=None, description="Price list for price_eur; the default list when omitted"
    )
    source_exported_at: AwareDatetime | None = Field(
        default=None,
        description="When the source system exported the file. Prices are valid from it; "
        "stock rows without their own time are as of it.",
    )
    dry_run: bool = Field(default=True, description="Validate and report without writing")


class ImportRowError(BaseModel):
    row: int
    field: str
    message: str


class ImportCounts(BaseModel):
    rows: int = 0
    products_created: int = 0
    products_updated: int = 0
    variants_created: int = 0
    variants_updated: int = 0
    prices_recorded: int = 0
    prices_unchanged: int = 0
    prices_older_ignored: int = 0
    stock_recorded: int = 0
    stock_unchanged: int = 0
    stock_older_ignored: int = 0
    errors: int = 0


class CatalogueImportResult(BaseModel):
    dry_run: bool
    total: int
    counts: ImportCounts
    errors: list[ImportRowError]
    import_run_id: uuid.UUID | None = Field(description="Set once applied")
    already_imported: bool = Field(
        default=False, description="The same file was already applied to this price list"
    )


class ImportRunOut(BaseModel):
    id: uuid.UUID
    source_kind: str
    filename: str | None
    file_sha256: str
    price_list_id: uuid.UUID | None
    source_exported_at: datetime | None
    counts: dict[str, Any]
    created_by_user_id: uuid.UUID | None
    created_at: datetime


class ImportRunPage(BaseModel):
    items: list[ImportRunOut]
    next_cursor: str | None
