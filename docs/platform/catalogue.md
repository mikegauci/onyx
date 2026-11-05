# Catalogue and inventory read model (PR-010)

The catalogue holds a workspace's products and their SKUs (variants), configurable VAT rates,
EUR price lists, prices and stock levels. Each price and stock figure is shown with where it
came from and when, so staff and later the quotation assistant can rely on it. **Missing data
stays missing:**

| Situation                        | Shown as                                       |
| -------------------------------- | ---------------------------------------------- |
| No price row for a SKU on a list | "Price not provided" (API: no `prices` entry)  |
| No stock row for a SKU           | "Stock unknown" (API: `availability: unknown`) |
| Product without a VAT rate       | "VAT not set" (API: `vat: null`)               |
| Stock 0 reported by the source   | "Out of stock"                                 |

Nothing is defaulted to zero, guessed or carried over from another tenant.

Members can browse products, SKUs, prices and stock. Owners and admins can also import
catalogue CSVs (`catalogue.import`) and manage VAT rates, price lists and archiving
(`catalogue.manage`). The API enforces permissions and the `catalogue` entitlement on every
route under `/v1/w/{slug}/catalogue`.

## VAT rates and price lists

- A VAT rate has a code (e.g. `STANDARD`), a name and a percentage (0–100, two decimals). The
  percentage **cannot be changed** after creation, so a stored rate keeps its meaning for
  history and later quotes; to change a rate, add a new code, move products to it by import, and
  archive the old one. Rates are tenant data; nothing in code assumes Malta's percentages.
- A price list has a code, a name, currency **EUR** (enforced by the database) and whether its
  prices **include VAT**, fixed at creation. Exactly one list is the default; the first list
  created becomes it. Imports put `price_eur` on the default list unless another is chosen.
- Money is stored as integer euro cents and exchanged as exact decimal strings (`"24.90"`).
  The dashboard displays the API's string; it does no price or VAT arithmetic.

## Catalogue imports

Download the example from the import screen (`/examples/catalogue.csv`, the same fictitious
20-SKU lighting catalogue the API tests import). Files must be UTF-8 CSV, up to 2 MB and 5,000
nonblank data rows, one row per SKU. Headers are case-insensitive and accept spaces.

| Column              | Meaning                                                                       |
| ------------------- | ----------------------------------------------------------------------------- |
| `sku`               | Required; 1–64 of `A-Z 0-9 . _ -`, stored upper case, unique per workspace    |
| `product_code`      | Required; groups SKUs into a product, same format as `sku`                    |
| `product_name`      | Required, up to 200 characters                                                |
| `variant_name`      | Optional SKU label, e.g. "6 W, 3000 K"                                        |
| `brand`, `category` | Optional, up to 100 characters                                                |
| `description`       | Optional, up to 2,000 characters                                              |
| `vat_code`          | Optional; must be an active VAT code of the workspace                         |
| `price_eur`         | Optional; digits with up to 2 decimals and a `.` (`1250.00`), no symbols      |
| `stock_available`   | Optional whole number                                                         |
| `stock_location`    | Optional, default `main`; lower-case `a-z 0-9 . _ -`                          |
| `stock_observed_at` | ISO 8601 with a time zone; when the source counted the stock                  |
| `attr_<name>`       | Any number (≤ 30) of attribute columns, e.g. `attr_wattage`, `attr_ip_rating` |

Rules:

- **Preview first.** The import is a dry run until confirmed; the preview reports what would be
  created, updated, recorded, left unchanged or ignored, and every row error (row number and
  column, never the cell's value). Invalid rows are skipped; valid rows are imported.
- **Blank means not provided.** A blank cell never clears a stored value or becomes zero.
  Attributes are merged into the SKU's existing attributes.
- Rows sharing a `product_code` must not contradict each other (name, brand, category,
  description, VAT code); a repeated SKU in the file is an error.
- A SKU already in the catalogue cannot move to another product through an import.
- **Authoritative times.** The optional _export time_ is when the source system produced the
  file. Prices are valid from it (or from the import time when not given). A stock figure needs
  an as-of time: its row's `stock_observed_at` or the export time; otherwise the row is
  rejected. Times in the future are rejected.
- **History, not overwrites.** Prices and stock levels are append-only. A new value is recorded
  only when it differs; data older than what is stored is ignored (counted as
  "older, not applied"), so an old export cannot roll prices or stock back.
- Importing the same file again into the same price list changes nothing and says so.
- Imports run one at a time per workspace. Each applied import is listed in _Import history_
  with the file name, a SHA-256 of the file, the export time, the price list, the changes and
  who ran it, and is written to the audit log (`catalogue.import.applied`).

Archiving a product hides it from the default product list; archiving a SKU removes it from the
product's SKU count. Exact SKU lookup still finds archived SKUs and marks them archived.

## API summary

| Route                                                        | Permission         |
| ------------------------------------------------------------ | ------------------ |
| `GET /products?q=&category=&include_archived`                | `catalogue.read`   |
| `GET /products/{id}`                                         | `catalogue.read`   |
| `GET /variants/by-sku/{sku}` (exact, any case)               | `catalogue.read`   |
| `GET /vat-rates`, `GET /price-lists`, `GET /imports`         | `catalogue.read`   |
| `POST /import` (dry run by default)                          | `catalogue.import` |
| `POST/PATCH /vat-rates…`, `POST/PATCH /price-lists…`         | `catalogue.manage` |
| `POST /products/{id}/archive`, `POST /variants/{id}/archive` | `catalogue.manage` |

Ids of another workspace behave like missing ones (404, or 422 when referenced in a body).

## Data model and isolation

Migration `0010` adds seven tenant-owned tables: `catalogue_vat_rates`,
`catalogue_price_lists`, `catalogue_import_runs`, `catalogue_products`, `catalogue_variants`,
`catalogue_prices` and `catalogue_stock_levels`.

- Every table has the standard tenant RLS policies gated by the `catalogue` module, so rows are
  invisible and unwritable outside the bound workspace or while the module is disabled.
- References between catalogue tables are composite foreign keys on `(organization_id, id)`;
  no row can point at another tenant's product, SKU, VAT rate, price list or import, even for
  the schema owner.
- `onyx_app` may read and insert, and update only editable columns (names, descriptions,
  attributes, default flag, archive markers). It cannot delete, change a VAT percentage, a price
  list's currency or VAT basis, a SKU or product code, an import run, or any price or stock row.
  Triggers make price and stock history append-only for every role.
- `onyx_worker` has no catalogue grants yet; connectors (PR-024) will add what they need.

## Migration and recovery

- Upgrade: `make db-migrate` (`alembic upgrade head`) applies `0010` after `0009`. It only
  creates new tables; existing data is untouched.
- Downgrade (`alembic downgrade 0009`) drops the seven tables **and their data**. Use it only on
  local or test databases. For a deployed database, recover by a reviewed forward migration or a
  backup restore.
- After merge, apply `0010` to the shared preview database (onyx-preview) with owner approval;
  it is not applied automatically.

## Verification

- `tests/modules/catalogue/test_domain.py`: codes, exact cents, time zones, CSV parsing and
  the sample catalogue (no invented values).
- `tests/api/test_catalogue_api.py`: exact SKU/price/VAT/stock/source visibility, sample import
  dry run and apply, idempotent re-import, history and older-data handling, VAT/price list
  rules, archiving, permissions and append-only history.
- `tests/api/test_catalogue_isolation.py`: two tenants and a user in both, via the API and
  direct SQL as the app role; composite keys; disabled module.
- `apps/platform/e2e/catalogue.spec.ts`: import with preview, exact values and gaps on the
  product page, member read-only access, module gate.
