# VA-007: deals and document chasing, implementation plan

Status: **approved 2026-11-25, in progress** · 2026-11-25 · Roadmap: `docs/roadmap-additions.md` (VA-007)

## Owner decisions (2026-11-25)

| Question           | Decision                                                                                     |
| ------------------ | -------------------------------------------------------------------------------------------- |
| Document checklist | A standard list that owners can edit per workspace.                                          |
| How customers send | A secure, expiring upload link, sent after staff approve the message. Staff can also upload. |
| Reminders          | A lightweight scheduler run by the existing API. No Temporal Cloud and no paid worker.       |
| Deposit            | Staff record it (amount, date, method and receipt). Onyx never takes money.                  |

## What a deal is

A deal is one sale to one customer. It is linked to a contact, and optionally to the lead,
the accepted quote, the conversation and, with the `automotive` module, the vehicle.

```text
reserved → deposit received → documents → finance → sold → collected
   └──────────────── cancelled (from any stage before sold) ──────────────┘
```

- **Finance** is skipped for cash deals: the deal has a flag for "financed in-house". When it
  is financed, VA-008 later adds the payment schedule here.
- Each stage change is recorded with who made it and when, and audited.
- A deal cannot move to **sold** while required documents are missing or not yet verified.
  Owners can override this with a reason, which is audited.
- **The vehicle:**
  - Reserving the deal marks the car **reserved**, and selling it marks it **sold**. The
    assistant stops offering it at once.
  - A website import never makes a car available again while an open deal holds it.
  - Cancelling the deal releases the hold, and the website status applies again.

## Documents

- **Standard checklist:** ID card or passport, driving licence and proof of address. A
  financed deal also needs its finance papers; a deal with a trade-in needs the trade-in
  logbook (registration document); and the deposit receipt is added when a deposit is
  recorded.
- **Workspace settings:** owners can rename items, mark them optional, or add their own items,
  each with a short note for the customer.
- **Each item's state:** missing → received → verified, or rejected with a reason (for example
  "blurred photo"). A rejection asks the customer again.
- **Storage:** files go to Supabase Storage, in a private bucket under the tenant's prefix.
  This is the existing `stored_files` design, and it adds the Supabase backend.
  - Files are encrypted at rest by the provider, and are never public.
  - Downloads go through the API after a permission check, with no public file links.
  - Accepted files are PDF, JPEG, PNG and HEIC, up to 10 MB each. The type is checked from the
    file's content, not its name.
- **Who sees what:** members see the deal and which items are missing. Only owners and admins
  open, verify or reject document files (a new `deals.documents` permission).

## Customer upload link

- Staff press **Request documents**. Onyx makes a link like `app.onyx.mt/u/<token>`:
  - Only the token's hash is stored.
  - The link expires after 7 days, and staff can revoke it.
  - It can only upload to that deal.
- The link is sent to the customer by WhatsApp (an approved utility template) or email. It
  goes through the existing approval step, so nothing leaves without a person.
- **The upload page:**
  - It shows the business name and the items still needed. It shows no personal data, no
    deal details and no files already uploaded.
  - Customers can upload from a phone camera.
  - Rate limits and size checks apply.
- Each upload creates a "document received" task for staff, and adds a note in the customer's
  conversation.

## Reminders (scheduler)

- **How it runs:** a protected endpoint, `POST /v1/internal/scheduler/run`, signed with a
  secret. A free GitHub Actions schedule calls it every 30 minutes, which also wakes the free
  Render instance. Each run is idempotent: the same reminder is never created or sent twice.
- **For each open deal with missing documents:**
  - After 2 days, a staff task: "Chase documents for <customer>".
  - If customer reminders are on, a reminder with the upload link: on day 2, then day 5, and
    at most 3 reminders in all.
  - These use an approved WhatsApp template or email, and respect the 24-hour window, opt-outs
    and the pilot controls (a new **Document reminders** switch; manual mode pauses it).
- **When it stops:** reminders stop as soon as the checklist is complete, or the deal is sold,
  collected or cancelled.
- **Retention:** document files are deleted automatically 180 days after a deal is collected or
  cancelled. The period is a workspace setting (30–3650 days). The deal record and the
  checklist states stay; only the files go, and that is logged.

## Data (migration 0029)

- `deals`:
  - The links: contact, lead, quote, conversation and vehicle.
  - Its state: the stage, financed, trade-in, the deposit (amount in cents, date, method) and
    the assignee.
  - Timestamps for each stage.
  - RLS by tenant, gated by a new `deals` module.
- `deal_events`: the stage history (append-only).
- `deal_documents`: one row per checklist item and deal, with its state, the stored file, who
  verified it and the rejection reason.
- `deal_settings`: the checklist template, the retention period and the reminder settings.
- `deal_upload_links`: the token hash, expiry, revocation and upload count.
- A public SECURITY DEFINER function resolves an upload token to its deal and missing items.
  It returns ids only.
- The automotive vehicle gets a `held_by_deal_id`, which the importer respects.
- **Rollback:** the downgrade drops the new tables. It refuses while any deals exist; after
  that, recovery is a forward fix.

## API and dashboard

- **Module:** a new `deals` module (it needs `crm`). The vehicle link is used when `automotive`
  is on, so other businesses can use deals for any sale.
- **API:**
  - Deals: list, create (from a contact, lead or accepted quote), change stage, record the
    deposit and cancel.
  - Documents: upload, download, verify, reject, request documents and revoke the link.
  - Settings, plus the public upload endpoints.
- **Dashboard:**
  - **Deals:** a board by stage, plus a list on phones.
  - **Deal page:** the stage controls, the deposit, the checklist with upload, verify and
    reject, the upload link, and the history.
  - **Create deal** from a quote ("Customer accepted → create deal") or a lead.
  - **Deals settings:** the checklist, retention and reminders.
  - The public **upload page**.
- **Guides:** the onboarding guide and the operator quick reference get a Deals section.

## Tests

- Tenant isolation: another tenant's deals, documents and links behave as missing, and so do
  file downloads.
- Permissions: a member cannot download or verify documents. A token reaches only its own
  deal's missing items.
- Links: expired, revoked and over-limit links are refused, and a file's type is checked from
  its content.
- The stage rules: sold is blocked while documents are missing; the owner override is audited.
- The vehicle hold: a reserved car is never offered, and the importer does not override the
  hold.
- The scheduler:
  - It is idempotent on re-runs.
  - Reminders stop when the checklist is complete, and respect opt-outs, manual mode and the
    switch.
  - Retention deletes the files and keeps the record.
- E2E covers the whole path:
  - create a deal from a quote, then request documents;
  - the customer uploads on the public page;
  - staff verify, then the deal is sold and collected.

## Parts (each its own PR)

1. **Deals core:** the migration, the deals API, the stage rules, the vehicle hold, the
   checklist and staff uploads with the Supabase Storage backend, the deals screens and tests.
2. **Customer upload link:** the token links, the public upload page, Request documents with
   the approved message, and tests.
3. **Scheduler:** the signed endpoint, the GitHub Actions schedule, document reminders,
   retention deletion, the pilot-controls switch, Insights figures for deals, and the guide
   updates.

## Owner actions

- **Supabase Storage:** create a private bucket `tenant-files` in each project and add the
  service key to Render (`ONYX_API_SUPABASE_SERVICE_KEY`; you set the value).
- **Scheduler secret:** add `ONYX_API_SCHEDULER_SECRET` on Render, and the same value as a
  GitHub Actions secret.
- **WhatsApp:** have a utility template approved for document requests and reminders, e.g.
  "Hi {{1}}, please upload your documents for your {{2}} here: {{3}}".
- **Ventur to confirm:** the exact documents they need, and how long they must keep them.

## Not in this PR

- Taking payments (VA-008 records payments; Onyx never collects money).
- E-signatures and contract generation.
- Virus scanning of uploads. The file type and size are checked; a scanner can be added later.

## Changes during implementation

- **Part 1:**
  - **Tasks:** "Check documents" tasks for owners and admins are created by the scheduler
    (part 3), because only the worker role may create tasks.
  - **Dashboard uploads:** these go through a server action, which Vercel caps at about 4.5 MB
    per request. Photos over 3 MB are resized in the browser. The customer upload page (part 2)
    goes straight to the API and accepts the full 10 MB.
  - **Plan:** the `deals` module is included in the Growth plan.
  - **API:** routes are under `/v1/w/{slug}/deals` (list and create), `/deals/{id}/…` and
    `/deals/settings`.
