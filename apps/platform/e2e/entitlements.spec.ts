import { E2E } from "../playwright.config";
import { HARBOUR, LUMEN, USERS, expect, signInAs, test } from "./fixtures";

const ADMIN_LUMEN = "/admin/organizations/lumen-lighting-test";

/** Restore Lumen's seeded entitlements through the API, whatever the test left behind. */
async function restoreLumen() {
  const session = await (
    await fetch(`${E2E.authUrl}/__e2e/session?email=${encodeURIComponent(USERS.pat)}`)
  ).json();
  for (const key of ["crm", "catalogue", "quotations"]) {
    const response = await fetch(
      `${E2E.apiUrl}/v1/admin/organizations/lumen-lighting-test/modules/${key}`,
      {
        method: "PUT",
        headers: {
          Authorization: `Bearer ${session.access_token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ enabled: true }),
      },
    );
    if (!response.ok) throw new Error(`restore ${key}: ${response.status}`);
  }
}

test.afterEach(restoreLumen);

test("disabling CRM hides it and denies it for that tenant only", async ({ browser }) => {
  const admin = await browser.newContext();
  await signInAs(admin, USERS.pat);
  const adminPage = await admin.newPage();
  await adminPage.goto(ADMIN_LUMEN);

  // Dependencies are enforced: CRM cannot go while Quotations needs it.
  await adminPage.getByRole("button", { name: "Disable CRM" }).click();
  await expect(adminPage.getByRole("alert").filter({ hasText: "quotations" })).toBeVisible();

  await adminPage.getByRole("button", { name: "Disable Quotations" }).click();
  await expect(adminPage.getByRole("button", { name: "Enable Quotations" })).toBeVisible();
  await adminPage.getByRole("button", { name: "Disable CRM" }).click();
  await expect(adminPage.getByRole("button", { name: "Enable CRM" })).toBeVisible();

  const owner = await browser.newContext();
  await signInAs(owner, USERS.olivia);
  const page = await owner.newPage();
  await page.goto(LUMEN);
  const nav = page.getByRole("navigation", { name: "Workspace" });
  await expect(nav.getByRole("link", { name: "Inbox" })).toBeVisible();
  await expect(nav.getByRole("link", { name: "CRM" })).toHaveCount(0);
  await page.goto(`${LUMEN}/m/crm`);
  await expect(page.getByRole("heading", { name: "Not found" })).toBeVisible();

  await page.goto(`${LUMEN}/settings/audit`);
  const audit = page.getByRole("table", { name: "Audit log" });
  await expect(audit.getByText("module.disabled").first()).toBeVisible();
  await expect(audit.getByText("Onyx staff").first()).toBeVisible();

  // Another tenant keeps its CRM.
  const other = await browser.newContext();
  await signInAs(other, USERS.sam);
  const harbour = await other.newPage();
  await harbour.goto(`${HARBOUR}/m/crm`);
  await expect(harbour.getByRole("heading", { level: 1, name: "CRM" })).toBeVisible();

  await Promise.all([admin.close(), owner.close(), other.close()]);
});

test("tenant settings show modules read-only", async ({ page, context }) => {
  await signInAs(context, USERS.olivia);
  await page.goto(`${LUMEN}/settings/modules`);
  const table = page.getByRole("table", { name: "Modules" });
  await expect(table.getByRole("row")).toHaveCount(6); // header + 5 modules
  await expect(page.getByRole("button", { name: /Enable|Disable/ })).toHaveCount(0);
});
