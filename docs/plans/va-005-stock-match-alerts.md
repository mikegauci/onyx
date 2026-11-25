# VA-005 — Stock-match alerts and sold-car follow-up

Status: part 1 merged (#88); part 2 built 2026-11-25. Depends on VA-001 (vehicles), PR-019 (WhatsApp) and PR-021
(scheduler), all merged.

## Owner decisions (2026-11-25)

- **Consent:** staff record it on the contact ("agreed to car alerts", with the date, how the
  customer agreed and who recorded it). A WhatsApp STOP reply withdraws it automatically.
  Nobody without recorded, unwithdrawn consent gets an alert or a follow-up template.
- **Sending:** staff approve. Matches wait in a list; staff send one or several with one click.
  Nothing sends automatically.
- **Criteria:** staff enter them on the lead. The assistant can also suggest criteria from the
  conversation; a suggestion counts only after staff confirm it.
- **Sold car:** people who asked about the car in the last 30 days and did not buy it are
  offered up to 3 similar available cars, also with staff approval. The reply is free-form
  inside WhatsApp's 24-hour window; otherwise it uses a marketing template and needs consent.
- **Ventur's own site:** the WordPress site is read-only to Onyx, so "the listing comes down" is
  delivered by VA-013 (the rebuilt site reads status from Onyx). Third-party sites stay out of
  scope.

## Part 1 — consent, wanted criteria, matching and new-car alerts

### Data (migration 0037)

- `crm_marketing_consents`: one row per contact and purpose (`car_alerts`). Columns:
  `granted_at`, `method` (`in_person`, `phone`, `whatsapp`, `email`, `form`), `note`,
  `recorded_by_user_id`, `withdrawn_at`, `withdrawn_via` (`staff`, `whatsapp_stop`). Tenant RLS
  and a same-tenant FK to the contact. Erasing a contact (privacy tools) deletes its rows.
- `automotive_wanted`: belongs to a lead (same-tenant FK). The criteria are all optional: make,
  model (case-insensitive exact match), `price_max_cents`, `year_min`, `mileage_max_km`, fuel.
  It also has `active`, `source` (`staff`, `assistant`), `confirmed_at` and `confirmed_by`. At
  least one criterion is required (check constraint).
- `automotive_matches`: `wanted_id`, `vehicle_id` and `status` (`pending`, `sent`, `dismissed`,
  `skipped`), plus `reasons` (jsonb), `sent_at`, `sent_by` and the outbound send id. Unique
  (`wanted_id`, `vehicle_id`), so each buyer gets at most one alert per car.
- `automotive_alert_settings`: the approved marketing template and the order of its parameters
  (name, car title, price, link).
- Permissions reuse existing ones (Onyx has owner, admin and member roles):
  - criteria, matches and consent follow `crm.read` and `crm.write` (everyone);
  - sending needs `outbound.approve` (admins and owners), so the click is the approval;
  - the alert template needs `inbox.manage`.

  The new tables are added to EXPECTED_TABLES.

### Matching (deterministic, `app/modules/automotive/matching.py`)

`match(wanted, vehicle) -> MatchResult(ok, reasons)` is a pure function:

- the car is `available` and not held by a deal;
- every criterion that is set holds: make and model compare case- and space-insensitively;
  price ≤ the maximum; year ≥ the minimum; mileage ≤ the maximum; fuel matches;
- a criterion with no value on the car fails. Missing data never counts as a match.

The reasons list each criterion and the car's value (for example "price €16,500 ≤ €18,000"),
and the matches list shows them. Unit tests cover each rule, the boundaries and missing values.

### When matching runs

The matches refresh when:

- an import run finishes, for new or changed available cars;
- staff save or confirm a wanted record, for that record;
- a scheduler pass is not needed in part 1: cars only arrive through imports, and criteria
  are matched as they are saved.

Rows are inserted with `ON CONFLICT DO NOTHING`. A match whose car is no longer available
becomes `skipped` before it is sent.

### Sending

`POST /v1/automotive/matches/send` takes up to 50 match ids. For each match, inside a
transaction:

1. Re-check the match rules, the car's availability and the contact's consent.
2. Skip the match, with a reason, if the contact has no WhatsApp conversation or number.
3. Send the approved marketing template through the existing send-once path
   (`whatsapp_send.begin/finish`).
4. Record a CRM activity.

A match that is already sent is a no-op. Every send is audited. The result returns
sent/skipped counts with reasons.

### API

- Consent: `GET` and `PUT /v1/crm/contacts/{id}/consents/car_alerts` (grant or withdraw).
- Wanted: create, update and deactivate on a lead, plus a list.
- Matches:
  - list per car, and across all cars with `status=pending`;
  - dismiss;
  - send.
- Settings: read and update `alert-settings`. The template must be approved, marketing and
  supported.

### STOP handling

The existing STOP words (STOP, UNSUBSCRIBE, IEQAF) already suppress the number. Now they also
withdraw the contact's consent, with `withdrawn_via = whatsapp_stop`. The withdrawn row is the
record, because the webhook has no acting user to audit. The message still lands in the inbox.

Sending uses the contact's latest conversation on the template's WhatsApp channel, reopened if
it was closed. A contact who never wrote on that number is skipped ("no WhatsApp
conversation"). Inbox templates stay utility-only everywhere else; only the alert send allows
a marketing template, after its consent check.

### Dashboard

- Contact page: a "Car alerts" consent panel (record or withdraw, with history).
- Lead page: a "Wanted" card to add, edit or deactivate criteria.
- Vehicle page: a "Matches" tab with reasons, consent state, and Send or Dismiss per match.
- A Matches page under Vehicles with every pending match and bulk send.
- Settings → Vehicles → Alerts: choose the template.

### Tests

- Matching rules: unit tests.
- API:
  - consent gate (no consent, withdrawn, granted);
  - one alert per car;
  - a sold car is skipped;
  - STOP withdraws consent;
  - a two-tenant negative test on every endpoint;
  - permission matrix and RLS checks;
  - model drift and the OpenAPI contract.
- Playwright: record consent, add criteria, see the match, send it with the fake WhatsApp
  provider.

## Part 2 — assistant suggestions, vehicle interest and sold-car follow-up

As built:

- Interest comes from the assistant (every available car its `search_vehicles` returned for
  the contact's conversation) and from staff (link a car on the lead). Deals are not needed:
  anyone with a deal on the sold car is excluded instead.
- Follow-ups are created when a car becomes sold, either through a website import or a deal
  (sold or collected). No scheduler is needed.
- Without the alert template, the free-form reply goes in the contact's latest WhatsApp thread.

- `automotive_vehicle_interests` (`contact_id`, `vehicle_id`, `conversation_id`, `source`,
  `last_at`) is recorded when the assistant's reply cites a car (the `search_vehicles` hits used
  in the reply), when staff link a car to a lead, or when a deal is opened.
- The assistant gains a `suggest_wanted` tool. It stores an unconfirmed wanted record
  (`source = assistant`) from what the customer said (make, model, budget and so on). It never
  invents values, and the record does not match until staff confirm it.
- When a car becomes `sold`, the next scheduler run lists the people interested in it in the
  last 30 days, excluding the buyer and anyone with an open deal. For each, up to 3 similar
  available cars are chosen by a deterministic similarity rule:
  - same make and body;
  - price within ±20%;
  - year within ±2.

  Ties break on the closest price, then the newest. The suggestions appear on the follow-up
  list for staff to send, either free-form inside the 24-hour window or as the marketing
  template with consent. Each person gets at most one follow-up per sold car (unique key).

## Owner actions (added to docs/owner-todo.md)

- A **marketing** WhatsApp template for car alerts, approved in WhatsApp Manager, for example:
  "Hi {{1}}, a {{2}} just arrived at Ventur for {{3}}. See it here: {{4}}. Reply STOP to opt
  out." Meta charges marketing messages per conversation.
- Agree with Ventur how customers give consent, and add car alerts to the privacy notice.

## Rollback

The migration downgrade drops the new tables (it refuses while sent matches exist, unless a
backup is restored). No existing table changes in part 1, apart from the erase function, which
also deletes consent rows.
