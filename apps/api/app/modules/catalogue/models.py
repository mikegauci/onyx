"""Catalogue tables: VAT rates, price lists, products, variants (SKUs), prices, stock, imports.

Every table is tenant-owned and gated by the ``catalogue`` module in its RLS policies.
References between catalogue tables are composite foreign keys on ``(organization_id, id)``,
as in the CRM, so a row can never point at another tenant's record.

Prices and stock levels are append-only history: each row says what a source reported and when
(``valid_from`` / ``observed_at``) and when Onyx recorded it (``recorded_at``). The current value
is the latest row; a missing row means "not provided" / "unknown", never zero.

Money is integer euro cents (``amount_minor``); never floats. A VAT rate's percentage cannot be
changed once created (the app role has no UPDATE on it), so a recorded rate keeps its meaning;
a new rate is a new code.
"""

import enum
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db.base import Base, created_at_column, str_enum, updated_at_column, uuid_pk

CODE_PATTERN = "^[A-Z0-9][A-Z0-9._-]{0,63}$"
CURRENCY = "EUR"
DESCRIPTION_MAX_LENGTH = 2000


class ImportSourceKind(enum.StrEnum):
    CSV = "csv"


def _organization_fk() -> Mapped[uuid.UUID]:
    return mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False, index=True
    )


def _user_fk() -> Mapped[uuid.UUID | None]:
    return mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)


def _same_tenant(column: str, table: str, name: str) -> ForeignKeyConstraint:
    return ForeignKeyConstraint(
        ["organization_id", column],
        [f"{table}.organization_id", f"{table}.id"],
        name=name,
        ondelete="RESTRICT",
    )


class VatRate(Base):
    """A tenant-configured VAT rate, e.g. code ``STANDARD`` at 18.00 %."""

    __tablename__ = "catalogue_vat_rates"
    __mapper_args__ = {"eager_defaults": True}  # noqa: RUF012
    __table_args__ = (
        UniqueConstraint("organization_id", "id"),
        UniqueConstraint("organization_id", "code"),
        CheckConstraint(f"code ~ '{CODE_PATTERN}'", name="code_format"),
        CheckConstraint("rate_percent >= 0 AND rate_percent <= 100", name="rate_range"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    organization_id: Mapped[uuid.UUID] = _organization_fk()
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    rate_percent: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    created_by_user_id: Mapped[uuid.UUID | None] = _user_fk()
    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = updated_at_column()
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class PriceList(Base):
    """A set of EUR prices. ``prices_include_vat`` is fixed at creation."""

    __tablename__ = "catalogue_price_lists"
    __mapper_args__ = {"eager_defaults": True}  # noqa: RUF012
    __table_args__ = (
        UniqueConstraint("organization_id", "id"),
        UniqueConstraint("organization_id", "code"),
        CheckConstraint(f"code ~ '{CODE_PATTERN}'", name="code_format"),
        CheckConstraint(f"currency = '{CURRENCY}'", name="currency_eur"),
        Index(
            "uq_catalogue_price_lists_one_default",
            "organization_id",
            unique=True,
            postgresql_where=text("is_default"),
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    organization_id: Mapped[uuid.UUID] = _organization_fk()
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, server_default=CURRENCY)
    prices_include_vat: Mapped[bool] = mapped_column(Boolean, nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    created_by_user_id: Mapped[uuid.UUID | None] = _user_fk()
    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = updated_at_column()


class ImportRun(Base):
    """One applied import: where the data came from and what it changed. Never edited."""

    __tablename__ = "catalogue_import_runs"
    __mapper_args__ = {"eager_defaults": True}  # noqa: RUF012
    __table_args__ = (
        UniqueConstraint("organization_id", "id"),
        _same_tenant(
            "price_list_id",
            "catalogue_price_lists",
            "fk_catalogue_import_runs_price_list_same_tenant",
        ),
        CheckConstraint("file_sha256 ~ '^[0-9a-f]{64}$'", name="sha256_format"),
        Index("ix_catalogue_import_runs_file", "organization_id", "file_sha256"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    organization_id: Mapped[uuid.UUID] = _organization_fk()
    source_kind: Mapped[ImportSourceKind] = mapped_column(
        str_enum(ImportSourceKind, "catalogue_import_source_kind"), nullable=False
    )
    filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    file_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    price_list_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    # When the source system exported the data, as stated by the person importing it.
    source_exported_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    counts: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    created_by_user_id: Mapped[uuid.UUID | None] = _user_fk()
    created_at: Mapped[datetime] = created_at_column()


class Product(Base):
    """A product, identified within the tenant by ``code``; sold as one or more variants."""

    __tablename__ = "catalogue_products"
    __mapper_args__ = {"eager_defaults": True}  # noqa: RUF012
    __table_args__ = (
        UniqueConstraint("organization_id", "id"),
        UniqueConstraint("organization_id", "code"),
        CheckConstraint(f"code ~ '{CODE_PATTERN}'", name="code_format"),
        _same_tenant(
            "vat_rate_id", "catalogue_vat_rates", "fk_catalogue_products_vat_rate_same_tenant"
        ),
        _same_tenant(
            "last_import_id", "catalogue_import_runs", "fk_catalogue_products_import_same_tenant"
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    organization_id: Mapped[uuid.UUID] = _organization_fk()
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    brand: Mapped[str | None] = mapped_column(String(100), nullable=True)
    category: Mapped[str | None] = mapped_column(String(100), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    vat_rate_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    last_import_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = updated_at_column()
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Variant(Base):
    """A sellable SKU of a product. ``attributes`` is a flat map of text values."""

    __tablename__ = "catalogue_variants"
    __mapper_args__ = {"eager_defaults": True}  # noqa: RUF012
    __table_args__ = (
        UniqueConstraint("organization_id", "id"),
        UniqueConstraint("organization_id", "sku"),
        CheckConstraint(f"sku ~ '{CODE_PATTERN}'", name="sku_format"),
        CheckConstraint("jsonb_typeof(attributes) = 'object'", name="attributes_object"),
        _same_tenant(
            "product_id", "catalogue_products", "fk_catalogue_variants_product_same_tenant"
        ),
        _same_tenant(
            "last_import_id", "catalogue_import_runs", "fk_catalogue_variants_import_same_tenant"
        ),
        Index("ix_catalogue_variants_product", "organization_id", "product_id"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    organization_id: Mapped[uuid.UUID] = _organization_fk()
    product_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    sku: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    attributes: Mapped[dict[str, str]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    last_import_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = updated_at_column()
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Price(Base):
    """A variant's price on a price list from ``valid_from``. Append-only (trigger)."""

    __tablename__ = "catalogue_prices"
    __mapper_args__ = {"eager_defaults": True}  # noqa: RUF012
    __table_args__ = (
        CheckConstraint("amount_minor >= 0", name="amount_non_negative"),
        _same_tenant("variant_id", "catalogue_variants", "fk_catalogue_prices_variant_same_tenant"),
        _same_tenant(
            "price_list_id", "catalogue_price_lists", "fk_catalogue_prices_price_list_same_tenant"
        ),
        _same_tenant(
            "import_run_id", "catalogue_import_runs", "fk_catalogue_prices_import_same_tenant"
        ),
        Index(
            "ix_catalogue_prices_current",
            "organization_id",
            "variant_id",
            "price_list_id",
            "valid_from",
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    organization_id: Mapped[uuid.UUID] = _organization_fk()
    variant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    price_list_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    amount_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    import_run_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    recorded_by_user_id: Mapped[uuid.UUID | None] = _user_fk()
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class StockLevel(Base):
    """Available quantity of a variant at a location as observed by a source. Append-only."""

    __tablename__ = "catalogue_stock_levels"
    __mapper_args__ = {"eager_defaults": True}  # noqa: RUF012
    __table_args__ = (
        CheckConstraint("location ~ '^[a-z0-9][a-z0-9._-]{0,63}$'", name="location_format"),
        _same_tenant(
            "variant_id", "catalogue_variants", "fk_catalogue_stock_levels_variant_same_tenant"
        ),
        _same_tenant(
            "import_run_id", "catalogue_import_runs", "fk_catalogue_stock_levels_import_same_tenant"
        ),
        Index(
            "ix_catalogue_stock_levels_current",
            "organization_id",
            "variant_id",
            "location",
            "observed_at",
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    organization_id: Mapped[uuid.UUID] = _organization_fk()
    variant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    location: Mapped[str] = mapped_column(String(64), nullable=False)
    quantity_available: Mapped[int] = mapped_column(Integer, nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    import_run_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    recorded_by_user_id: Mapped[uuid.UUID | None] = _user_fk()
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
