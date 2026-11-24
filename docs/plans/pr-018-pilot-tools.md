# PR-018: pilot tools, implementation plan

Status: **approved 2026-11-24, in progress** · Roadmap: `PR_ROADMAP.md` (PR-018), `docs/roadmap-additions.md`

PR-018 lets Onyx run a supervised pilot with the first client (Ventur). Staff use Onyx on real
enquiries while the owner watches results and can turn any part off at once. The pilot gate is
one real enquiry taken all the way to an approved, sent quote, with the outcomes recorded and the
client signing off or the defects tracked.

## Owner decisions (2026-11-24)

| Question | Decision                                                                                                                       |
| -------- | ------------------------------------------------------------------------------------------------------------------------------ |
| Scope    | Insights page, feature switches, manual mode and written guides                                                                |
| Guides   | Two guides: an operator guide (a short daily quick reference) **and** an onboarding guide (how to use the system), both as PDF |

## What gets built

### 1. Insights (Overview → Insights, `/w/{slug}/insights`)

All figures are worked out from existing records when the page loads, for the last 7, 30 or
90 days. No new tracking tables are added, so the numbers can't drift from the records.

- **Enquiries:** new conversations by channel (WhatsApp, email, phone, other).
- **Response time:** median and 90th percentile from a customer's first message to the
  first reply sent by staff. Automatic messages (text-back) are counted separately, so they
  don't flatter the figure.
- **Replies from the assistant:** sent as written, sent after an edit, rejected, expired, still
  waiting. Also how long a draft waited for approval (median).
- **Assistant hand-offs:** runs that drafted versus runs that handed over to staff, and the
  most common reasons.
- **Quotes:** created, approved, sent and accepted. This is the pilot-gate funnel.
- **Missed calls:** calls, WhatsApp text-backs, SMS text-backs, and skipped calls with their reasons.
- **Baseline:** the owner can enter "before Onyx" figures (typical first-reply time and
  enquiries per week) so the page can show the change, e.g. "4 min, was about 2 h".

Every workspace member can see Insights; only owners and admins can edit the baseline. Tenant
isolation comes from the usual RLS session, and every query is scoped to the workspace.

### 2. Feature switches (Settings → Pilot controls)

These are per-workspace switches, separate from the plan's modules: they pause a feature
without changing billing. Owners and admins can flip them, and so can a platform admin.

- **Assistant:** when off, "Ask the assistant" is refused and the button explains why.
- **Missed-call text-back:** when off, missed calls are still logged and create a task, but no
  message goes out, and the skip reason says "paused".

Each change is audited (who, when, an optional reason) and shown on the page. Later automatic
features (VA-002 auto-send, VA-003 web chat replies) add their own switch here.

### 3. Manual mode (humans only)

One switch, owner/admin, that overrides every automatic feature without losing the individual
switch settings. With manual mode on:

- the assistant is refused, and so are automatic messages such as text-back;
- messages still arrive in the inbox, and staff reply, approve and send as normal;
- a banner across the workspace says "Manual mode: Onyx is not drafting or sending anything
  automatically".

Turning manual mode off restores the previous switches. This is the roadmap's "rollback to
manual service". It takes effect on the next request, with no redeploy.

### 4. Guides

- **Onboarding guide:** a step-by-step tour of the system for a new client, with screenshots
  from sample data. It covers signing in, the overview, the inbox and channels, contacts and
  leads, vehicles and the catalogue, the assistant and approvals, quotes, tasks, knowledge,
  settings and members, insights, and pilot controls.
- **Operator guide:** a two-page quick reference covering the daily routine, approve, edit or
  reject, missed-call tasks, manual mode, and what to do when something looks wrong.

Both are written once in Markdown (`docs/guides/`), shown in the app under **Help**
(`/w/{slug}/help`), and exported to PDF by a script (`pnpm guides:pdf`) so they can be
emailed or printed. They are written for any client; nothing in them is specific to Ventur.

### 5. Pilot runbook (docs)

`docs/operations/pilot-runbook.md` covers the pilot itself:

- client data onboarding steps (import vehicles, contacts, knowledge);
- the UAT checklist;
- the end-to-end acceptance script (enquiry → lead → grounded answer → quote → approval → send);
- the outcome log template;
- the sign-off and defect tracking.

## Data (migration 0027)

- `workspace_controls`: one row per organisation, RLS by tenant. Columns:
  - `manual_mode`, `assistant_enabled` and `text_back_enabled`;
  - `baseline_first_reply_minutes` and `baseline_enquiries_per_week` (nullable);
  - `updated_by_user_id` and `updated_at`.
- A missing row means the defaults: everything on and manual mode off.
- The worker gets SELECT only, so the text-back path can check the switches.
- Rollback: the downgrade drops the table. Nothing existing changes shape.

## API

- `GET /v1/w/{slug}/controls` (reader) and `PATCH /v1/w/{slug}/controls` (owner/admin, audited).
- `PATCH /v1/admin/organizations/{slug}/controls` (platform admin, audited).
- `GET /v1/w/{slug}/insights?days=7|30|90` (reader).
- The assistant run endpoint returns `409 feature_paused` when the assistant is off or manual
  mode is on. The missed-call connector records a skip reason of `paused` in the same cases.

## Tests

- **Controls:** defaults, owner/admin can change them, a member can't, a change is audited, and
  another tenant can't read or change them.
- **Manual mode:** the assistant is refused; a missed call is logged with a task but nothing is
  sent; turning it off restores the earlier switches.
- **Insights:** known seeded data gives exact counts and medians; data from other tenants and
  outside the range is excluded; text-back is excluded from the staff response time.
- **E2E:** turn on manual mode → banner shown → assistant button disabled → turn off → normal.
  The Insights page shows the seeded figures.

## Parts

1. **Backend and dashboard** (one PR):
   - Backend: the migration, controls, insights, enforcement and tests.
   - Dashboard: the Insights page, Settings → Pilot controls, the manual-mode banner and the
     paused assistant state.
2. **Guides and runbook:** the Markdown, the Help pages, the PDF export and the screenshots.

## Changes during implementation

- **Permissions:** existing ones are reused. `workspace.read` reads the controls and Insights,
  and `workspace.update` (owners and admins) changes them, so no new permission was added.
- **Platform admin endpoint:** `PUT /v1/admin/organizations/{slug}/manual-mode` sets manual mode
  only, as Onyx support's kill switch. The feature switches stay with the workspace's owners
  and admins.
- **Insights scope:** only enabled modules are queried; a module the plan lacks shows no section.

## Not in this PR

- Time tracking per staff member. "Time spent" is measured as the wait for approval and the
  response time, not by timers.
- CSV export of insights.
- Live charts over time; v1 shows totals for the chosen range.
