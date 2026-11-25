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

## Scheduler (part 3)

`POST /v1/internal/scheduler/run`, with `Authorization: Bearer <ONYX_API_SCHEDULER_SECRET>`
(compared in constant time; without the setting it answers 404). A GitHub Actions schedule
(`.github/workflows/scheduler.yml`, every 30 minutes, free) calls it, which also wakes the free
Render API. `scheduler_deal_tenants()` (SECURITY DEFINER, worker only) lists active tenants with
`deals` on; each runs in its own worker transaction, so one failure never blocks the others.
Jobs (`app/modules/deals/jobs.py`) are idempotent:

- **Check documents:** one task for owners/admins per received, unchecked document (same key as
  a customer upload's task).
- **Chase documents:** a task for staff when an open deal still misses required documents 2 days
  after it was created; at most one a week, urgent after the first week.
- **Retention:** files of deals collected or cancelled more than `retention_days` ago (default 180) are deleted; the checklist item keeps `file_deleted_at`, the deal records
  `documents_deleted`.

Insights shows deals (new, sold, collected, cancelled, open) and customer uploads.

## Part 4 (later)

Automatic customer reminders with a fresh upload link, through an approved WhatsApp utility
template, once Meta approves the document template (owner decision, 2026-11-25).
