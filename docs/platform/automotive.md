# Vehicles (VA-001)

The `automotive` module holds a car dealer's vehicle stock and imports it from their website.
It requires `catalogue` and has its own entitlement, so the shared catalogue never assumes
vehicles. Part 1 is the backend; part 2 the screens (see [Screens](#screens)).

**Not yet run against Ventur's live site.** Tests use a fake Vehica site. The first live
import needs the owner's go-ahead.

## Vehicles

One row per listing, matched to the site by its WordPress post id (`source_ref` `wp:{id}`):
title, stock number, VIN, make, model, variant, year, mileage (km), engine (cc), fuel,
transmission, body type, colour, doors, condition, price in cents (empty for "price on
request"), features, photos (ordered, https only, at most 30), video, listing link and status:

| Status      | Meaning                                                    |
| ----------- | ---------------------------------------------------------- |
| `available` | Listed and for sale                                        |
| `reserved`  | Listed, marked reserved by the field map's `reserved` rule |
| `sold`      | Marked sold by the field map's `sold` rule                 |
| `withdrawn` | No longer on the site; kept, never deleted                 |

`field_sources` records, for each field, where its value came from and when
(`{"mileage_km": {"source": "wordpress:vehica_6664", "at": "…"}}`).

## Importing from WordPress (Vehica theme)

1. `PUT /v1/w/{slug}/automotive/source` (`catalogue.import`) with the site's address and,
   optionally, a field map. The address must be `https` on a public host.
2. `POST …/import/preview`: fetches every listing and reports what would be created,
   updated, left unchanged and withdrawn, with a sample of changes. Nothing is written.
3. `POST …/import/apply`: fetches again and applies. Only changed fields are written.
   Running it again with nothing changed at the site changes nothing. Each applied import is
   recorded (`automotive_import_runs`, counts only) and audited (`automotive.import.applied`).

The listings come from the site's public REST API (`/wp-json/wp/v2/cars`, 100 per page, at
most 5,000), and taxonomy terms (make, model, fuel…) are resolved by id. Site data is
untrusted: each field is parsed and bounded, and a field that cannot be read stays empty
instead of being guessed. The assistant treats listing text as data, never instructions.

**SSRF guard.** The server fetches only `https` URLs on port 443 whose host resolves to
public addresses only (no private, loopback, link-local or metadata addresses), checked when
the source is saved and again at every import. It never follows redirects and caps every
response at 5 MB.

### Field map

Which Vehica field holds what. The default is Ventur's, read from its public API on
20 November 2026:

| Field        | Vehica field   | Kind                        |
| ------------ | -------------- | --------------------------- |
| make         | `vehica_6659`  | term                        |
| model        | `vehica_6660`  | term                        |
| condition    | `vehica_6654`  | term                        |
| body_type    | `vehica_6655`  | term                        |
| transmission | `vehica_6662`  | term                        |
| fuel         | `vehica_6663`  | term                        |
| colour       | `vehica_6666`  | term                        |
| doors        | `vehica_12770` | term (number from the name) |
| features     | `vehica_6670`  | terms                       |
| year         | `vehica_14696` | number                      |
| mileage_km   | `vehica_6664`  | number                      |
| engine_cc    | `vehica_6665`  | number                      |
| stock_number | `vehica_6671`  | text                        |
| price_cents  | `vehica_6656`  | price                       |
| photos       | `vehica_6673`  | urls                        |
| video_url    | `vehica_6674`  | video                       |

**To confirm with Ventur:** which field marks a car sold or reserved (add a rule such as
`"sold": {"field": "vehica_6657", "values": ["Sold"]}`), and what `vehica_16721`,
`vehica_18820`, `vehica_26685` and `vehica_37874` hold. Until a sold rule exists, every
listed car is `available` and a car taken off the site becomes `withdrawn`.

## Screens

- **Vehicles** (`catalogue.read`): cards with the first photo, summary (year, mileage, fuel,
  transmission), price or "Price on request", status and stock number; search by make, model
  or stock number and filter by status (available by default). Each car has a page with all
  photos, its details, features and a link to the listing on the website.
- **Import from website** (`catalogue.import`): the website address and, under "Field map
  (advanced)", the field map as JSON; **Preview import** shows how many listings would be
  new, changed, unchanged or no longer listed, with a sample; **Import these changes**
  applies them. Errors reading the site are explained in plain words.

For local runs and e2e, `ONYX_API_AUTOMOTIVE_SITE=fake` imports from a built-in demo site of
four fictitious cars (refused when deployed). `apps/platform/e2e/vehicles.spec.ts`: an owner
connects the site, previews, imports and re-imports (nothing changes), a member browses and
searches without the import page, and an http address is refused.

## The assistant

Where `automotive` is on, the assistant gets `search_vehicles(query, max_price_eur)`. It
returns at most 5 **available** cars (never sold, reserved or withdrawn ones) with year,
mileage, fuel, transmission, price (or "on request"), up to 3 photos and the listing link.

## Permissions

| Action                   | Permission         |
| ------------------------ | ------------------ |
| List and read vehicles   | `catalogue.read`   |
| Connect the site, import | `catalogue.import` |

## Data (migration `0025`)

`automotive_sources`, `automotive_vehicles`, `automotive_import_runs`, all with tenant
policies gated by `automotive`; the app role reads and writes them. Rollback: revert the PR;
`0025` downgrades locally.

## Tests

- `tests/modules/automotive/test_vehica.py`: parsing (terms, numbers, prices in cents,
  photos, video), missing and implausible values left empty, unusable listings skipped, the
  sold rule, the SSRF guard (http, credentials, ports, private, loopback, metadata, IPv6,
  mixed addresses).
- `tests/api/test_automotive.py` (real database, fake site over two pages): preview writes
  nothing; apply maps every field with its source; re-running changes nothing; a price
  change updates one field; a car taken off the site is withdrawn, not deleted; the
  assistant's search never returns a sold car; permissions, the module gate and tenants; the
  SSRF guard refuses before any request; field map validation.
