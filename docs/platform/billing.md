# Billing (PR-026)

Onyx charges tenants through **Stripe Billing**. A tenant's plan decides its modules and its
included AI budget. Part 1 is the backend; part 2 the screens (see [Screens](#screens)).

**Not connected to Stripe yet.** Tests use a fake provider. Going live needs the owner's
Stripe account, the plans' prices (test mode first) and the webhook endpoint registered.

## Plans

Defined in `app/core/billing/plans.py` (placeholders until the owner decides):

| Plan    | Modules                                                                   | AI per month |
| ------- | ------------------------------------------------------------------------- | ------------ |
| Starter | CRM, inbox                                                                | $0           |
| Growth  | CRM, inbox, catalogue, quotations, outbound replies, assistant, knowledge | $50          |

Prices live in Stripe; `ONYX_API_STRIPE_PRICE_STARTER` / `_GROWTH` map each plan to its price.
A plan's modules always include what they require (`tests/test_billing_plans.py`).

**Without an active subscription** (cancelled, unpaid, never subscribed after a cancellation)
a tenant keeps CRM and the inbox, so its customers' conversations stay reachable, and its AI
budget is 0. Statuses `active`, `trialing` and `past_due` keep the plan.

**Plans decide modules.** Each subscription change sets the tenant's modules to the plan's
exactly. A module a platform admin switched on by hand stays on only until the next plan
change. Every change is audited as `module.enabled` / `module.disabled` with
`"by": "billing"`.

## Who can do what

| Action                                       | Permission       | Roles        |
| -------------------------------------------- | ---------------- | ------------ |
| See the plan, status and the AI usage report | `billing.read`   | Owner, admin |
| Start a checkout, open the billing portal    | `billing.manage` | Owner only   |

Return links must be on an allowed dashboard origin (`ONYX_API_CORS_ORIGINS`), so a checkout
cannot send anyone to another site.

## API

| Request                                      | Answer                                                             |
| -------------------------------------------- | ------------------------------------------------------------------ |
| `GET /v1/w/{slug}/billing`                   | Plan, status, period end, the plans on offer                       |
| `POST /v1/w/{slug}/billing/checkout`         | `{"url"}`: a Stripe Checkout page for a plan                       |
| `POST /v1/w/{slug}/billing/portal`           | `{"url"}`: the Stripe billing portal (409 before a first checkout) |
| `GET /v1/w/{slug}/billing/usage?month=…`     | AI usage by day and workload, totals and the budget                |
| `GET /v1/w/{slug}/billing/usage.csv?month=…` | The same as CSV, with a total line                                 |

Without Stripe settings, `GET …/billing` says `configured: false` and the rest answer `503`.

## Screens

- **Settings → Billing** (owners and admins): the plan, its status and renewal or end date,
  the plans on offer, and the AI usage report by month with a CSV download (through the
  dashboard, so the browser never holds an API token). Owners get **Choose {plan}**, which
  opens Stripe Checkout, and **Manage billing**, which opens the billing portal once there is
  a customer. Admins see everything but cannot change it.
- After checkout the page says the plan updates as soon as the payment is confirmed: the
  webhook, not the redirect, changes the plan.
- **Admin → organisation → Billing** (platform admins): plan, status, period end and whether
  a Stripe customer exists, read-only (`GET /v1/admin/organizations/{slug}/billing`, migration
  `0024`).

E2E (`apps/platform/e2e/billing.spec.ts`, fake provider): Harbour's owner chooses Growth, comes
back from the fake checkout, a signed subscription webhook applies Growth (quotations appear
in the sidebar), the CSV downloads, and a cancellation returns Harbour to CRM and inbox.

## Webhooks

`POST /v1/webhooks/stripe`, in this order:

1. The `Stripe-Signature` is checked (HMAC-SHA256 of `"{t}.{body}"`), and a timestamp more
   than 5 minutes off is refused (`401`). Bodies over 512 KB get `413`.
2. The tenant is found through Onyx's own customer mapping (`billing_customers`). A
   `checkout.session.completed` creates the mapping from the `client_reference_id` Onyx set
   when creating the checkout. A subscription event that arrives first uses the tenant id
   Onyx put in the subscription's metadata. A customer never moves to another tenant.
3. In one `onyx_worker` transaction bound to that tenant: the event id is recorded once
   (`app_billing_record_event`); a duplicate changes nothing. An event older than the last
   one applied (Stripe does not guarantee order) is recorded and skipped. Otherwise the
   subscription is stored and the plan applied (`app_billing_apply_plan`).
4. Any error rolls everything back and answers `500`, so Stripe retries.

Handled: `checkout.session.completed`, `customer.subscription.created`, `.updated`, `.deleted`.
Others are acknowledged and ignored.

## AI usage report

Sums the month's `ai_usage_events` by day and workload: calls, tokens and cost in millionths of
a US dollar. It is computed from the same rows the AI gateway's budget uses, so the report
reconciles exactly with the budget. Money is formatted from integers, never floats.

## Setup (owner)

1. Stripe (test mode): create the two products with monthly prices, and copy the price ids.
2. Developers → API keys: the secret key. Webhooks → add endpoint
   `https://<api>/v1/webhooks/stripe` with the four events above; copy its signing secret.
3. Render → `onyx-api-preview` → Environment: `ONYX_API_STRIPE_API_KEY`,
   `ONYX_API_STRIPE_WEBHOOK_SECRET`, `ONYX_API_STRIPE_PRICE_STARTER`,
   `ONYX_API_STRIPE_PRICE_GROWTH`.
4. Stripe → Settings → Billing → Customer portal: turn on plan changes and cancellations.

## Data (migration `0023`)

- `billing_customers` (one per tenant), `billing_subscriptions` (one per tenant): tenant
  policies; the app role reads them; the worker writes them.
- `billing_webhook_events`: event ids, once. Row-level security with no policies; only
  `app_billing_record_event` touches it.
- Worker functions: `app_billing_customer_tenant`, `app_billing_record_event`,
  `app_billing_apply_plan`.

Rollback: revert the PR; `0023` downgrades locally. Deployed databases use a forward fix.

## Tests

`tests/api/test_billing.py` (real database, fake Stripe): owners start checkout and nobody
else can, return links must be on the dashboard; a subscription applies its plan and budget;
duplicate events change nothing; downgrades, late older events, upgrades and cancellation in
event order; bad, missing and old signatures; a customer stays with its tenant and a
conflicting claim is refused; the portal; the usage report and CSV reconcile with the stored
events, other tenants excluded; billing off without settings; money formatting.
