import { createHmac } from "node:crypto";

import { E2E, STRIPE_E2E_PRICES, STRIPE_E2E_SECRET } from "../playwright.config";
import { HARBOUR, USERS, expect, signInAs, test } from "./fixtures";

// The e2e API uses the in-memory fake billing provider: nothing reaches Stripe. Harbour is used
// because its seeded modules (CRM and inbox) are the base the test ends on after cancelling.
test.setTimeout(120_000);

const HARBOUR_ID = "harbour-catering-test";

async function subscriptionEvent(
  organizationId: string,
  kind: string,
  price: string,
  created: number,
) {
  const payload = JSON.stringify({
    id: `evt_e2e_${created}_${kind}`,
    type: kind,
    created,
    data: {
      object: {
        id: "sub_e2e_harbour",
        customer: "cus_e2e_harbour",
        status: "active",
        cancel_at_period_end: false,
        metadata: { organization_id: organizationId },
        items: { data: [{ price: { id: price }, current_period_end: created + 30 * 86400 }] },
      },
    },
  });
  const t = Math.floor(Date.now() / 1000);
  const signature = createHmac("sha256", STRIPE_E2E_SECRET).update(`${t}.${payload}`).digest("hex");
  const response = await fetch(`${E2E.apiUrl}/v1/webhooks/stripe`, {
    method: "POST",
    headers: { "Content-Type": "application/json", "Stripe-Signature": `t=${t},v1=${signature}` },
    body: payload,
  });
  expect(response.status).toBe(200);
}

/** Harbour's organisation id, read as a platform admin (never guessed). */
async function harbourId(): Promise<string> {
  const session = await (
    await fetch(`${E2E.authUrl}/__e2e/session?email=${encodeURIComponent(USERS.pat)}`)
  ).json();
  const orgs = await (
    await fetch(`${E2E.apiUrl}/v1/admin/organizations`, {
      headers: { Authorization: `Bearer ${session.access_token}` },
    })
  ).json();
  return orgs.find((o: { slug: string }) => o.slug === HARBOUR_ID).id;
}

test("an owner checks out, the plan applies from the webhook, and cancelling restores the base", async ({
  page,
  context,
}) => {
  await signInAs(context, USERS.hugo);
  await page.goto(`${HARBOUR}/settings/billing`);
  await expect(page.getByRole("heading", { name: "Billing", exact: true })).toBeVisible();
  const plans = page.getByRole("list", { name: "Plans" });
  await plans.getByRole("button", { name: "Choose Growth" }).click();
  // The fake provider sends the browser straight back, as Stripe does after paying.
  await expect(page).toHaveURL(/checkout=done/);
  await expect(page.getByRole("status").filter({ hasText: "Thank you" })).toBeVisible();

  const id = await harbourId();
  const now = Math.floor(Date.now() / 1000);
  await subscriptionEvent(id, "customer.subscription.created", STRIPE_E2E_PRICES.growth, now);
  await page.reload();
  await expect(page.getByText("Active", { exact: true })).toBeVisible();
  await expect(plans.getByRole("button", { name: "Current plan" })).toBeDisabled();
  await expect(page.getByRole("button", { name: "Manage billing" })).toBeVisible();
  // Growth switched on the quotations module for Harbour.
  await expect(
    page.getByRole("navigation").getByRole("link", { name: "Quotations" }),
  ).toBeVisible();

  // The usage report downloads as CSV through the dashboard.
  const csv = await page.request.get(`${HARBOUR}/settings/billing/usage.csv`);
  expect(csv.status()).toBe(200);
  expect(await csv.text()).toContain("day,workload,calls");

  await subscriptionEvent(id, "customer.subscription.deleted", STRIPE_E2E_PRICES.growth, now + 1);
  await page.reload();
  await expect(page.getByText("Cancelled", { exact: true })).toBeVisible();
  await expect(page.getByRole("navigation").getByRole("link", { name: "Quotations" })).toHaveCount(
    0,
  );
});
