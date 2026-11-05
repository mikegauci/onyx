# Quotations and PDF preview (PR-012)

Staff prepare quotes for CRM contacts from the catalogue, an approver freezes them, and
anyone with access can open a PDF preview. **Nothing is sent to a customer**; sending after
approval comes with PR-016/PR-017. There is no AI in this module yet.

The `quotations` module requires `crm` and `catalogue`. The API enforces the entitlement and
permissions on every route under `/v1/w/{slug}/quotations`.

| Permission           | Roles                | Allows                                                   |
| -------------------- | -------------------- | -------------------------------------------------------- |
| `quotations.read`    | member, admin, owner | Quotes, versions, PDF preview, settings (read)           |
| `quotations.write`   | member, admin, owner | Draft and edit, revise, record accepted/declined, cancel |
| `quotations.approve` | admin, owner         | Approve; give discounts above the workspace limit        |
| `quotations.manage`  | admin, owner         | Number prefix, validity days, member discount limit      |

## Lifecycle

```text
draft ── approve ──▶ approved ── accept / decline ──▶ accepted | declined
  ▲                    │
  └──── revise ────────┘   (new draft version; the approved one is superseded)
draft | approved ── cancel ──▶ cancelled
```

- A quote has a number per workspace and year (`Q-2026-0001`; the prefix is a setting).
- Only the current **draft** version can change. Approving freezes it: a database trigger
  rejects any later change to the version or its lines, even by the schema owner, except
  marking it `superseded` when a revision starts. Versions are never deleted.
- Revising copies the lines into version _n_ + 1 as a draft. Earlier versions stay readable,
  with their PDF.
- Accepting an approved quote after its `valid_until` date is refused: revise it first so
  prices and stock are checked again.

## Lines and snapshots

- **Catalogue lines** name a SKU. When a line is added (or refreshed), Onyx copies the
  current price on the quote's price list (with the price row id and its `valid_from`), the
  product's VAT rate (code and percentage) and the description. A SKU with no price on the
  list, or no active VAT rate, cannot be added.
- **Custom lines** (delivery, installation) have a staff-entered description, unit price and
  one of the workspace's VAT rates.
- Quantity is 1-100,000. Discounts are percentages with two decimals. Members may give up to
  the workspace limit (default 10 %); approvers may give more.
- Each version keeps whether its prices include VAT, copied from the price list when the
  version was created.

## Exact totals

`app/modules/quotations/pricing.py` is the only place money is calculated. It uses integer
cents and `Decimal`, rounding half-up to the cent:

1. `list = unit price * quantity`
2. `discount = round(list * discount % / 100)`, then `after = list - discount`
3. VAT **per line**, then summed:
   - prices exclude VAT: `net = after`, `vat = round(net * rate / 100)`
   - prices include VAT: `gross = after`, `net = round(gross * 100 / (100 + rate))`,
     `vat = gross - net`
4. Quote totals are sums of the lines; the VAT breakdown groups them by code and rate.

A draft's totals are computed on every read. Approval stores them on the version, and the
tests recompute the stored totals from the line snapshots to prove they reproduce exactly.
The dashboard displays the API's decimal strings and does no arithmetic.

Example (prices include VAT at 18 %): 2 × €129.00 = €258.00 gross, net €218.64, VAT €39.36.

## Stale prices and stock

Each draft line is compared with the catalogue now:

| Warning              | Blocks approval | Resolve by                    |
| -------------------- | --------------- | ----------------------------- |
| `price_changed`      | yes             | "Use current price" or remove |
| `price_missing`      | yes             | remove (or add a price)       |
| `vat_changed`        | yes             | "Use current price" or remove |
| `sku_archived`       | yes             | remove                        |
| `sku_missing`        | yes             | remove                        |
| `stock_unknown`      | no              | the approver confirms it      |
| `out_of_stock`       | no              | the approver confirms it      |
| `insufficient_stock` | no              | the approver confirms it      |

The quote keeps its snapshot until a person decides; nothing changes silently. Approval
needs the version number the approver is looking at, so a stale screen cannot approve a
changed draft. Confirmed warnings are stored on the version and in the audit entry.

## PDF preview

`GET /quotes/{id}/versions/{n}/pdf` renders that version with ReportLab (BSD licence, no
system libraries) from the stored snapshots only. Drafts carry a "DRAFT - not a valid offer"
watermark. Tenant text is escaped before rendering. The dashboard serves it through a route
handler that forwards the signed-in user's token; the API checks access.

## Data

Migration `0012` creates `quotations_settings`, `quotations_counters`, `quotations_quotes`,
`quotations_versions` and `quotations_lines`: tenant RLS gated by the module, composite
same-tenant keys to CRM contacts/customers/leads, catalogue price lists/SKUs/VAT rates and to
each other, column-limited update grants, delete only for draft lines, and the two triggers
above. CRM and catalogue data are read only through `crm/public.py` and
`catalogue/public.py`. `onyx_worker` has no access yet.

Downgrade drops the five tables (local and test only). Deployed databases recover by forward
fix or backup restore. The preview database gets `0012` only after merge, with approval.

## Seed data

Lumen has one draft, **Q-2026-0001** "Lobby chandelier replacement" for Clara Borg: 2 ×
ARC-P-30-BRS and a half-day installation, €338.00 including VAT.

## Tests

- `tests/modules/quotations/test_domain.py`: worked pricing examples, rounding, 500 random
  quotes for consistency and reproducibility, lifecycle, every warning code.
- `tests/api/test_quotations_api.py`: drafting, validation, discount policy, warnings and
  approval, price refresh, stored totals reproduced from snapshots, revisions, outcomes,
  expiry, PDF, settings, audit.
- `tests/api/test_quotations_isolation.py`: two tenants through the API and SQL, composite
  keys, grants, frozen versions even for the owner, per-tenant numbering, the module gate.
- `apps/platform/e2e/quotations.spec.ts`: draft, stock warning, approve, PDF, revise; members
  cannot approve or manage settings.
