import { LUMEN, USERS, expect, setLumenModule, signInAs, test } from "./fixtures";

// VA-006 part 1: the estimate matches Ventur's website; a finance application on a deal
// switches its checklist to the applicant type's documents.
test.setTimeout(150_000);
test.beforeEach(() => setLumenModule("deals", true));
test.afterEach(() => setLumenModule("deals", false));

test("staff work out an estimate and start a finance application on a deal", async ({
  page,
  context,
}) => {
  await signInAs(context, USERS.olivia);
  await page.goto(`${LUMEN}/m/deals/finance`);
  const calc = page.getByRole("form", { name: "Finance estimate" });
  await calc.getByLabel("Vehicle price (€)").fill("16500");
  await calc.getByLabel("Deposit (€)").fill("3000");
  await calc.getByLabel("Years", { exact: true }).fill("5");
  await calc.getByRole("button", { name: "Work out the estimate" }).click();
  await expect(page.getByText("€318.38")).toBeVisible({ timeout: 30_000 });

  await page.goto(`${LUMEN}/m/deals/new`);
  await page.getByLabel("Customer").selectOption({ label: "Clara Borg" });
  await page.getByLabel(/Financed in-house/).check();
  await page.getByRole("button", { name: "Create deal" }).click();
  await expect(page.getByRole("heading", { name: /Clara Borg/ })).toBeVisible({ timeout: 30_000 });
  const dealUrl = page.url();
  await page.getByRole("link", { name: "Start a finance application" }).click();
  await page.getByLabel("Marital status").selectOption("married");
  await page.getByLabel("Price (€)").fill("16500");
  await page.getByLabel("Deposit (€)").fill("3000");
  await page.getByLabel("Years", { exact: true }).fill("5");
  await page.getByLabel("Net monthly income (€)").fill("2500");
  await page.getByRole("button", { name: "Start finance application" }).click();
  await expect(page.getByRole("heading", { name: /Finance · Clara Borg/ })).toBeVisible({
    timeout: 30_000,
  });
  await expect(page.getByText("€318.38").first()).toBeVisible();
  await expect(page.getByText("€2,500.00")).toBeVisible();

  await page.goto(dealUrl);
  const checklist = page.getByRole("list", { name: "Checklist" });
  await expect(checklist).toContainText("Last 3 months payslips");
  await expect(checklist).toContainText("Spouse ID Card");
  await expect(checklist).not.toContainText("Finance papers");
  await expect(page.getByRole("link", { name: "Download the blank form" }).first()).toBeVisible();
});
