# VA-010 — Daily owner summary

Status: built 2026-11-26. Depends on VA-001 (vehicles) and VA-008 (finance schedules), both
merged.

## Goal

Once a day, in Malta time, Onyx sends the owner one short message by email or WhatsApp
covering:

- the day's enquiries by channel;
- cars reserved and sold;
- payments recorded;
- listings added and removed;
- Facebook and Instagram posts.

Acceptance (from the roadmap):

- the totals match the underlying records;
- the summary is sent once per day in Malta time;
- a missing source is reported as missing, not as zero.

## Decisions (defaults; the owner can change them in settings)

- **Send time:** 19:00 in the workspace's timezone (Europe/Malta for Ventur). The summary covers
  the workspace's calendar day so far, from 00:00 to the moment it is built.
- **Recipients:** one to five workspace members chosen in settings. Each one gets it by email (to
  their account address), by WhatsApp (to a phone number entered for them), or both. Off by
  default.
- **No staff approval:** the summary goes to the business's own staff, not to customers, so it
  does not wait in a list. It contains counts and amounts only: no customer names, phone numbers
  or message text.
- **Facebook and Instagram:** Onyx has no Meta page access yet, so this source is always
  reported as "not connected". Reading posts through the Graph API is a follow-up once page
  access is granted (owner action).

## Data (migration 0043)

- `automotive_vehicle_events`: one row each time a vehicle is first listed or changes status:
  - `vehicle_id`;
  - `kind`: `listed` (first seen) or `status`, with `from_status` and `to_status`;
  - `source`: `import` or `deal`;
  - `occurred_at`.

  These rows are written by the WordPress import and by the deal hooks that hold or release a
  car. Without them, "listings removed" cannot be counted: a vehicle only stores its current
  status. Counting starts when the migration is applied, so the summary for that first day
  only counts changes made after it. Only the current day is ever worked out (earlier days
  are kept as sent).

- `owner_summary_settings` (one per workspace):
  - `enabled` and `send_at` (a local time, default 19:00);
  - `recipients`, a list of up to 5 members, each with an email flag and an optional WhatsApp
    number in E.164 form;
  - the WhatsApp utility template and its parameters.
- `owner_summaries`: one row per workspace and local date (unique), holding:
  - the figures (JSONB);
  - the status: `sent`, `partly_sent` or `failed`;
  - the per-recipient results;
  - `sent_at`.

  The unique date guarantees the summary goes once a day, even if the scheduler runs twice or
  is retried. The stored figures are what was sent, which makes it possible to check them
  later.

All tables use tenant RLS with same-tenant foreign keys. The scheduler worker gets
INSERT/UPDATE on `owner_summaries` and INSERT on `automotive_vehicle_events`.

## Figures (pure where possible, unit-tested)

New module `app/core/insights/daily.py`. Each section either has a value or is `missing` with a
reason. Each section counts records whose timestamp falls in the local day, converted to UTC
bounds.

| Section          | Source                                                                                                           | Missing when                           |
| ---------------- | ---------------------------------------------------------------------------------------------------------------- | -------------------------------------- |
| Enquiries        | `inbox_conversations.created_at`, by channel kind; missed calls                                                  | inbox module off; no channel connected |
| Reserved         | `deal_events` with kind `created` (to `reserved`)                                                                | deals module off                       |
| Sold             | `deals.sold_at`                                                                                                  | deals module off                       |
| Payments         | `finance_payments.created_at`, not voided: count and total in cents                                              | deals module off                       |
| Listings         | `automotive_vehicle_events`: added = listed or back on sale; removed = to sold or withdrawn; stock available now | automotive module off                  |
| Facebook / Insta | none yet                                                                                                         | always "not connected"                 |

The enquiries query reuses the same SQL as Insights (`insights.service.enquiries`) with an end
bound added, so the two pages can never disagree.

## Sending

- The scheduler (every 30 minutes) calls `owner_summary.run_due(now)` for each tenant. It runs
  when:
  - the summary is enabled;
  - the local time is past `send_at`;
  - and there is no row for today.

  A run that is missed (for example, GitHub's cron is late) catches up later the same local day,
  never the next day. `RunSummary` gains `owner_summaries`.

- **Email:** sent through the platform mailer (Resend) from the workspace's sender, to each
  recipient's account email. This is not an inbox conversation, because it is internal.
- **WhatsApp:** sent through the workspace's WhatsApp channel to the recipient's number. A
  free-form message is only allowed inside the 24-hour window, so it needs an approved
  **utility** template that has a parameter for the summary text. Without one, WhatsApp for that
  recipient is skipped with the reason `no_template`.
- Each recipient and channel is sent with an idempotency key `summary:{org}:{date}:{user}:{channel}`.
  One failure does not stop the others, and the status records what happened.
- **Message:** a short plain-text block in the workspace's language (English), for example:

  ```
  Ventur — Thursday 26/11/2026
  Enquiries: 14 (WhatsApp 9, email 3, missed calls 2)
  Reserved: 2 · Sold: 1
  Payments: 3 recorded, €1,450.00
  Listings: +2 added, −1 removed (37 available)
  Facebook/Instagram: not connected
  ```

## API and dashboard

- `GET` and `PUT /v1/w/{ws}/insights/daily-summary/settings` (owners and admins).
- `GET /v1/w/{ws}/insights/daily-summary/preview`: today's figures so far, without sending.
- `POST /v1/w/{ws}/insights/daily-summary/test`: sends today's preview to the current user only,
  marked "test". It does not create the day's row.
- `GET /v1/w/{ws}/insights/daily-summary/history`: the last 30 summaries and what was sent.
- Dashboard: Insights → **Daily summary**, with settings, the preview, "Send me a test" and
  the history.

## Tests

- Unit:
  - local-day bounds across the DST change (the last Sunday of March and of October);
  - the "is it due" rule;
  - message rendering, with missing sections shown as "not set up" or "not connected",
    never "0".
- API, against the real database:
  - totals match seeded records, including a voided payment that is excluded, a deal sold
    yesterday that is not counted, and a withdrawn listing;
  - two scheduler runs send once;
  - a run before `send_at` sends nothing;
  - email and WhatsApp with and without a template;
  - one recipient failing does not block another;
  - permissions: members cannot change settings;
  - a two-tenant negative test on every endpoint;
  - RLS, EXPECTED_TABLES, model drift and the OpenAPI contract.
- Import: a re-import with no change writes no vehicle events; a removed listing writes one
  `withdrawn` event.

## Owner actions

- Choose the recipients and send time, and turn the summary on.
- Optional: an approved WhatsApp **utility** template for the summary, with one text parameter.
- Later: grant Meta page access for Facebook/Instagram posts (follow-up item).

## Out of scope

- Reading Facebook and Instagram posts (needs Meta page access).
- Weekly or monthly summaries, charts and PDF attachments.

## Rollback

Revert the code first, then run the migration downgrade, which drops the three new tables. No
existing table changes.
