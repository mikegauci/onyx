import { HARBOUR, LUMEN, USERS, expect, signInAs, test } from "./fixtures";

test("signed-out visitors are sent to sign-in", async ({ page }) => {
  await page.goto(LUMEN);
  await expect(page).toHaveURL(/\/login\?next=%2Fw%2Flumen-lighting-test/);
});

test("owner navigates the workspace shell and settings", async ({ page, context }) => {
  await signInAs(context, USERS.olivia);
  await page.goto(LUMEN);

  await expect(
    page.getByRole("heading", { level: 1, name: "Lumen Lighting (test)" }),
  ).toBeVisible();
  const nav = page.getByRole("navigation", { name: "Workspace" });
  for (const label of ["Overview", "CRM", "Catalogue", "Inbox", "Quotations", "Settings"]) {
    await expect(nav.getByRole("link", { name: label })).toBeVisible();
  }

  await nav.getByRole("link", { name: "CRM" }).click();
  await expect(page.getByText("CRM is on its way")).toBeVisible();

  await nav.getByRole("link", { name: "Settings" }).click();
  await expect(page).toHaveURL(`${LUMEN}/settings/general`);
  await expect(page.getByLabel("Workspace name")).toHaveValue("Lumen Lighting (test)");

  const settings = page.getByRole("navigation", { name: "Settings" });
  await settings.getByRole("link", { name: "Members" }).click();
  const members = page.getByRole("table", { name: "Workspace members" });
  await expect(members.getByRole("row")).toHaveCount(5); // header + 4 members
  await expect(members.getByText("hugo.owner@harbour.example.test")).toHaveCount(0);

  await settings.getByRole("link", { name: "Audit log" }).click();
  await expect(page.getByRole("heading", { name: "Audit log" })).toBeVisible();
  await expect(page.getByRole("navigation", { name: "Breadcrumb" })).toContainText("Audit log");
});

test("member sees no settings and cannot open them by URL", async ({ page, context }) => {
  await signInAs(context, USERS.mia);
  await page.goto(LUMEN);
  const nav = page.getByRole("navigation", { name: "Workspace" });
  await expect(nav.getByRole("link", { name: "Overview" })).toBeVisible();
  await expect(nav.getByRole("link", { name: "Settings" })).toHaveCount(0);

  await page.goto(`${LUMEN}/settings/members`);
  await expect(page.getByRole("heading", { name: "Not found" })).toBeVisible();
});

test("switching workspace re-resolves role and settings", async ({ page, context }) => {
  await signInAs(context, USERS.sam);
  await page.goto(LUMEN);
  const nav = page.getByRole("navigation", { name: "Workspace" });
  await expect(nav.getByRole("link", { name: "Settings" })).toHaveCount(0); // member here

  await page.getByRole("button", { name: /Switch workspace/ }).click();
  await page.getByRole("menuitem", { name: "Harbour Catering (test)" }).click();
  await expect(page).toHaveURL(HARBOUR);
  await expect(
    page.getByRole("heading", { level: 1, name: "Harbour Catering (test)" }),
  ).toBeVisible();
  await expect(nav.getByRole("link", { name: "Settings" })).toBeVisible(); // admin here
});

test("another tenant's workspace is not found", async ({ page, context }) => {
  await signInAs(context, USERS.hugo);
  await page.goto(LUMEN);
  await expect(page.getByRole("heading", { name: "Not found" })).toBeVisible();
  await expect(page.getByText("Lumen Lighting (test)")).toHaveCount(0);
});

test("admin saves settings and the change is audited", async ({ page, context }) => {
  await signInAs(context, USERS.sam);
  await page.goto(`${HARBOUR}/settings/general`);
  await page.getByLabel("Timezone").selectOption("Europe/Rome");
  await page.getByRole("button", { name: "Save changes" }).click();
  await expect(page.getByRole("status").getByText("Workspace settings saved.")).toBeVisible();

  await page.goto(`${HARBOUR}/settings/audit`);
  const audit = page.getByRole("table", { name: "Audit log" });
  await expect(audit.getByText("workspace.updated").first()).toBeVisible();
  await expect(audit.getByText("Sam Consultant").first()).toBeVisible();
});

test("invalid settings show the API's field error", async ({ page, context }) => {
  await signInAs(context, USERS.olivia);
  await page.goto(`${LUMEN}/settings/general`);
  await page.getByLabel("Workspace name").fill("   ");
  await page.getByRole("button", { name: "Save changes" }).click();
  await expect(page.getByLabel("Workspace name")).toHaveAttribute("aria-invalid", "true");
});
