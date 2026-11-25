# Deals (VA-007)

A deal is one sale to one customer, from reservation to collection, with the customer's
documents. Module `deals` (requires `crm`; included in the Growth plan). Plan:
`docs/plans/va-007-deals-and-documents.md`.

## Stages

`reserved → deposit_received → documents → finance → sold → collected`, or `cancelled` before
sold. Rules live in `app/modules/deals/lifecycle.py` (pure, tested):

- open stages can move to any other open stage (fixing mistakes); `finance` only when financed;
  `deposit_received` only with a recorded deposit (recording one moves a reserved deal on);
- `sold` needs every required document verified, unless an **owner** overrides with a reason
  (recorded in the history and audit log);
- `sold → collected` only; `collected` and `cancelled` are final. Cancelling needs a reason.

## Vehicle hold

With `automotive`, a deal can reserve a car: the car becomes `reserved` and
`automotive_vehicles.held_by_deal_id` points at the deal. While held, the website import never
changes its status or withdraws it. Sold → the car is `sold`; collected → hold released (stays
sold); cancelled → hold released and the car is `available` (the next import applies the site's
status). A partial unique index allows one open deal per car.

## Documents

- Checklist per deal from the workspace template (`deal_settings.checklist`, or the standard
  list: ID, licence, proof of address; deposit receipt once a deposit is recorded; finance
  papers when financed; trade-in logbook with a trade-in). Items can be added per deal.
- States: missing → received → verified, or rejected (with a reason). Re-uploading replaces the
  file (the old object is deleted).
- Files: PDF, JPEG, PNG or HEIC (checked from the bytes), at most 10 MB, stored through
  `TenantFileService` under `tenants/<org>/<file>`. Backends: Supabase Storage (private bucket,
  service key; preview and production), local folder (development), memory (tests). Deployed
  without the key, uploads return 503.
- Who: members create deals, move stages and upload; only owners and admins (`deals.documents`)
  open, verify or reject files. Each opening is audited (`deals.document_opened`). The dashboard
  streams files through a route handler with the user's token; nothing is cached.
- The dashboard upload goes through a server action (Vercel's ~4.5 MB request cap), so photos
  over 3 MB are resized in the browser; larger PDFs wait for the customer upload link (part 2).

## Coming in parts 2 and 3

Customer upload links and the public upload page; the scheduler for document tasks, customer
reminders and retention deletion (`deal_settings.retention_days`, default 180 days after a deal
closes).
