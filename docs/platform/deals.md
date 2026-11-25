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

## Customer upload link (part 2)

- **Request documents** on a deal makes a link `app.onyx.mt/u/<token>`:
  - It is valid for 7 days and allows 30 uploads. Making a new link stops the old one, and
    staff can stop a link at any time. Selling the deal ends it too.
  - The token is 256 random bits, shown to staff once; only its SHA-256 is stored.
- **Sending:** staff copy the link, or tick "Prepare a reply" to create a reply with the link in
  the customer's conversation. The reply waits for approval as usual. Outside WhatsApp's 24-hour
  window it must go as an approved template.
- **The public page** (`/u/[token]`, no sign-in, not indexed, no referrer):
  - It shows only the business name and the documents still needed (missing or rejected, with
    the reason). It shows no names, deal details or uploaded files.
  - Files go straight from the phone to the API (`PUT /v1/public/uploads/{token}/documents/{id}`),
    up to 10 MB each, type-checked from the bytes.
- **Resolving the token:** the API uses `deal_upload_link_lookup` (SECURITY DEFINER, worker
  only) and then works in a worker transaction bound to that tenant. Every invalid, expired,
  revoked, used-up or sold-deal link gets the same 404.
- **After an upload:** the document becomes "received" (from the customer), the deal's history
  records it, and owners and admins get a "Check … for …" task.

## Coming in part 3

The scheduler: tasks to chase missing documents, customer reminders, and retention deletion
(`deal_settings.retention_days`, default 180 days after a deal closes).
