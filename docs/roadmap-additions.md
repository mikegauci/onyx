# Roadmap additions

This file lists work the owner approved **outside** the 28 numbered PRs in `PR_ROADMAP.md`. That file is the planning kit and is kept verbatim. Items here follow the same rules as the roadmap (`CLAUDE.md`, `CLAUDE_WORKFLOW.md`): one item at a time, plan before edits, executable evidence, a draft PR, and no merge or deploy without the owner's approval.

| ID       | Phase      | Title                                         | Depends on                    | Effort     | Status                                                               |
| -------- | ---------- | --------------------------------------------- | ----------------------------- | ---------- | -------------------------------------------------------------------- |
| DF-001   | Foundation | Design foundation: research, tokens, base UI  | PR-001                        | 6–10h      | Merged [mikegauci/onyx#2](https://github.com/mikegauci/onyx/pull/2)  |
| SITE-001 | Marketing  | Build the Onyx Studio landing page (onyx.mt)  | DF-001 (and PR-002 to deploy) | 20–32h     | Landing page live on onyx.mt 2026-11-23; copy awaits owner review    |
| VA-001   | Ventur     | Vehicle stock extension and WordPress import  | PR-010                        | 16–28h     | Merged (#42, #43, #44); live import awaits Ventur sold-field mapping |
| VA-002   | Ventur     | Auto-send policy for low-risk AI replies      | PR-015, PR-016                | 12–20h     | Paused by the owner 2026-11-23; partial work reverted                |
| VA-003   | Ventur     | Web chat channel and embeddable widget        | PR-011, VA-002                | 16–28h     | Approved 2026-11-19, not started                                     |
| VA-004   | Ventur     | Missed-call text-back                         | PR-019                        | 8–14h      | Merged ([#64](https://github.com/mikegauci/onyx/pull/64)); go-live needs a +356 number      |
| VA-005   | Ventur     | Stock-match alerts and sold-car follow-up     | VA-001, PR-019, PR-021        | 14–24h     | Approved 2026-11-19, not started                                     |
| VA-006   | Ventur     | Finance pre-qualification intake              | PR-015                        | 8–14h      | Approved 2026-11-19, not started                                     |
| VA-007   | Ventur     | Deals and document chasing                    | VA-001, PR-021                | 24–40h     | Approved 2026-11-19, not started                                     |
| VA-008   | Ventur     | In-house finance schedules and reminders      | VA-007                        | 14–24h     | Approved 2026-11-19, not started; payment record source unknown      |
| VA-009   | Ventur     | Review requests and service/renewal reminders | VA-007, PR-021                | 14–22h     | Approved 2026-11-19, not started                                     |
| VA-010   | Ventur     | Daily owner summary                           | VA-001, VA-008                | 10–18h     | Approved 2026-11-19, not started                                     |
| VA-011   | Ventur     | Voice agent with phone menu                   | VA-004, VA-001, VA-002        | 30–55h     | Needs separate approval after VA-004                                 |
| VA-012   | Ventur     | Website audit; redevelopment if justified     | VA-001                        | audit 3–5h | Replaced by VA-013 (owner, 2026-11-24)                               |
| VA-013   | Ventur     | Rebuild ventur.com.mt on Onyx stock           | VA-001                        | 30–50h     | Approved 2026-11-24, not started; needs a plan                       |

### DF-001 — Design foundation

- **Approved:** 2026-11-04, to land before PR-007.
- **Scope:** `docs/design/ui-references.md`, design tokens in `packages/ui/src/styles/globals.css`, a WCAG contrast test, base shadcn components, Geist fonts, a System/Light/Dark theme toggle that defaults to the device preference (both apps). No product features or dashboard routes.

### SITE-001 — Build the Onyx Studio landing page

- **Approved:** 2026-11-04 by the owner, as a new item outside the 28-PR roadmap.
- **Depends on:** DF-001 merged (tokens and components). Deploying to a non-production URL needs PR-002. Live DNS for onyx.mt needs separate approval.
- **Estimated implementation:** 20–32h (rough order of magnitude, excludes waiting for copy, logos or legal text).
- **Implementation:** a single page in `apps/site`, following the direction in `docs/design/ui-references.md` §1:
  - glass nav;
  - hero with animated headline and product mock of the approval queue;
  - "how it works" flow (Enquiry → AI draft → Staff approval → Order → Fulfilment) with an animated beam;
  - module bento grid;
  - trust strip and pilot quote;
  - pricing cards (display only; values from config, not hard-coded logic);
  - CTA band;
  - footer with company and legal/privacy links.

  Use Motion and selected Magic UI components (MIT, copied in via the shadcn CLI), site only; no WebGL in v1. Metadata, Open Graph image and sitemap/robots.

- **Content:** the owner supplies or approves all copy, pricing, the pilot quote and any customer logos. Use placeholders clearly marked as such until then. No fake testimonials or logos.
- **Acceptance:**
  - Lighthouse (mobile) Performance ≥ 90, Accessibility ≥ 95, Best Practices ≥ 95, SEO ≥ 95 on a production build.
  - All animations stop under `prefers-reduced-motion`; content stays readable with JS disabled.
  - Keyboard navigation and visible focus work throughout; no horizontal scroll at 360px.
  - Vitest smoke tests for sections; a Playwright smoke test that loads the page and checks CTAs link to the platform URL.
  - `make check`, `make test`, `pnpm build` pass.
- **Non-goals:** CMS, blog, multi-language, contact form that stores data (needs a GDPR/privacy decision first), analytics/cookies (needs a consent decision), live DNS changes.
- **PR checklist:** tests; accessibility evidence; screenshots (desktop and mobile, with motion and with reduced motion); documentation; human review.

## Order changes to the numbered roadmap

- **20 November 2026, owner decision:** finish the multi-tenant platform before onboarding
  clients. Order: PR-025 → PR-020/PR-021 → PR-027 → PR-026 → PR-018 (the first client's
  pilot) → PR-028. PR-025 no longer waits for PR-018: onboarding is how the pilot client is
  set up. PR-022 to PR-024 (orders, fulfilment, POS) wait for a retail client.

## Ventur Auto Import (VA items)

- **Approved:** 2026-11-19 by the owner. Ventur Auto Import (ventur.com.mt), a Malta car dealer, replaces the lighting retailer as the first tenant.
- **Owner decisions:** low-risk AI replies send without approval (VA-002); Ventur finances cars in-house, and where payment records live today is unknown; they have a basic phone system and use WhatsApp; website redevelopment only if VA-012 shows significant improvements.
- **Current site:** WordPress with the Vehica car-dealer theme, Elementor and WooCommerce. Listings can be read from WordPress before any redevelopment.
- **Effect on the numbered roadmap:** PR-019 (WhatsApp) and PR-020/PR-021 (Temporal) moved earlier (now done). For this tenant, VA-007 replaces PR-022/PR-023 (retail orders, stock reservations, fulfilment) and VA-001's WordPress import replaces PR-024's first adapter. PR-018 (pilot) runs with Ventur. PR-025–PR-028 are unchanged.
- **Placement:** car-specific data and behaviour go in an `automotive` extension module with its own entitlement. The shared core must not assume vehicles.

### Order

Already done on the platform (20 November 2026): PR-019 WhatsApp, PR-020/PR-021 Temporal
workflows and tasks, PR-025 onboarding, PR-026 billing, PR-027 part 1 hardening.

1. VA-001 vehicle stock
2. VA-002 auto-send policy
3. VA-003 web chat
4. PR-018 supervised pilot with Ventur on WhatsApp and web chat (Meta business verification
   must be done by then)
5. VA-004 missed-call text-back
6. VA-005, VA-006, VA-007, VA-008, VA-009, VA-010
7. VA-011 voice agent, only after VA-004 has run in production

VA-013 (site rebuild) replaces the VA-012 audit. It can run at any time after VA-001 and does not block anything.

### VA-001 — Vehicle stock extension and WordPress import

- **Implementation:** an `automotive` module adding a vehicle record to the catalogue: stock number, VIN, make, model, variant, year, mileage, fuel, transmission, body, colour, price, photos (ordered), listing URL and status (`available`, `reserved`, `sold`, `withdrawn`). Import from the WordPress site (Vehica listings through the WordPress REST API, or CSV export as a fallback), with preview, idempotent re-runs and a recorded source and time for each field.
- **Acceptance:** a full import of Ventur's live listings with every price, mileage and status matching the site; re-running changes nothing; missing data stays missing; the assistant can search vehicles and return photos and the listing link; a sold car is never offered as available.

### VA-002 — Auto-send policy for low-risk AI replies

- **Implementation:** a per-tenant policy, off by default: an allowlist of intents that may send without approval (stock and availability questions, photos, listing links, opening hours, directions, viewing requests). A reply auto-sends only when every deterministic check passes (grounding, price, stock, citation). Everything else is held or escalated: price negotiation, trade-in values, finance terms, complaints, legal or warranty claims, angry or confused customers, and low-confidence answers. Includes a kill switch, per-conversation and per-hour send limits, a "sent automatically" label, after-the-fact review and an audit record for every auto-send.
- **Acceptance:** evaluation cases for each allowlisted and blocked intent in English and Maltese, including prompt injection, stale prices and sold cars; the kill switch stops sending within one request; turning the policy off restores approval for every reply.

### VA-003 — Web chat channel and embeddable widget

- **Implementation:** a web chat channel in the inbox and a small script-tag widget that works on the current WordPress site and any future site. Anonymous visitor sessions, optional contact capture, rate limits and abuse protection, a privacy notice, staff takeover, and photo/link cards for vehicles.
- **Acceptance:** a visitor asks about a car in Maltese or English and gets a grounded answer with photos and the link; staff can take over; messages are tenant-isolated; the widget meets accessibility checks and does not slow the host page noticeably.

### VA-004 — Missed-call text-back

- **Implementation:** Ventur's carrier forwards unanswered calls (conditional forwarding) to a cloud number. The caller gets a WhatsApp message (or SMS fallback) inviting them to continue in chat, and staff get a WhatsApp summary with the caller's number and any history.
- **Owner actions:** confirm the carrier supports conditional call forwarding; choose and pay for the cloud number provider.
- **Acceptance:** an unanswered test call produces one customer message and one staff summary, with no duplicates on retries.

### VA-005 — Stock-match alerts and sold-car follow-up

- **Implementation:** saved "wanted" criteria on leads (make, model, budget, year, mileage, fuel). When a matching vehicle arrives, opted-in buyers get a WhatsApp template message. When a car is sold, its listing comes down on Ventur's own site and recent enquirers are offered similar cars. Third-party listing sites are out of scope unless they offer an API.
- **Acceptance:** matching is deterministic and explainable; nobody without marketing consent is messaged; each buyer gets at most one alert per car.

### VA-006 — Finance pre-qualification intake

- **Implementation:** the chat collects income, deposit, preferred term and the car of interest, then creates a summary for the finance clerk. The assistant never approves, declines or quotes credit terms.
- **Acceptance:** a completed intake creates one summary visible only to permitted staff; incomplete intakes are flagged; data protection notice and retention are applied.

### VA-007 — Deals and document chasing

- **Implementation:** a deal record per sale: reserved → deposit received → documents → finance → sold → collected. A per-deal document checklist (ID, deposit proof, finance papers), a secure, expiring customer upload link, encrypted private storage, staff verification, and reminders for missing documents through Temporal.
- **Acceptance:** documents are visible only to permitted staff of the tenant; links expire; reminders stop when the checklist is complete; retention and deletion rules are documented and tested.

### VA-008 — In-house finance schedules and reminders

- **Implementation:** a payment schedule per financed deal, imported from wherever Ventur keeps it today (to be confirmed) or entered by staff. Staff record payments received; Onyx does not take payments. Reminders before the due date and when overdue, with staff-controlled wording and pausing.
- **Open question:** where payment records live today (spreadsheet, accounting software or paper).
- **Acceptance:** amounts are exact decimals; reminders never go to a customer who has paid; every reminder is logged.

### VA-009 — Review requests and service/renewal reminders

- **Implementation:** a Google or Facebook review request a week after collection. A customer-vehicle record with licence, insurance and service due dates, with reminders. Optional partner offers (for example Globowax) only for customers with marketing consent.
- **Acceptance:** each customer gets at most one review request per sale; reminders respect opt-out; offers are clearly marked.

### VA-010 — Daily owner summary

- **Implementation:** an end-of-day summary by WhatsApp or email: enquiries by channel, cars sold and reserved, payments recorded, listings added or removed, and Facebook/Instagram posts (Meta Graph API with page access).
- **Acceptance:** totals match the underlying records; the summary sends once per day in Malta time; missing sources are reported as missing, not zero.

### VA-011 — Voice agent with phone menu

- **Implementation:** phone menu (1 sales, 2 import orders, 3 accounts); if sales doesn't answer, a voice assistant answers from live stock, takes the caller's details and sends staff a WhatsApp summary.
- **Risks:** Maltese speech quality, latency, call-recording consent, telephony cost. Needs a separate plan and approval after VA-004 has run in production.

### VA-012 — Website audit; redevelopment if justified

- **Implementation:** audit ventur.com.mt (speed, mobile, SEO, listing structure, lead capture). Recommend redevelopment only if the gains are significant; a rebuilt site would read vehicle stock from Onyx, so sold cars come down automatically.

### VA-013 — Rebuild ventur.com.mt on Onyx stock

- **Approved:** 2026-11-24. The owner chose a full rebuild instead of the VA-012 audit.
- **Implementation:** a new Next.js site for Ventur Auto Import that reads vehicle stock from Onyx through a read-only, tenant-scoped public endpoint, so sold and reserved cars update on the site without manual edits. It includes stock search and filters, a vehicle page with photos and specs, and enquiry capture into the Onyx inbox (and web chat once VA-003 exists). It is fast, accessible and mobile-first, with SEO metadata and redirects from the old WordPress URLs.
- **Owner actions:** Ventur's approval and branding, the domain and DNS, and content (about, finance, contact pages). Decide whether Onyx Studio hosts it.
- **Needs a plan:** hosting, CMS for non-stock pages, URL migration, and the public stock endpoint's tenant and rate-limit design.
