import { HARBOUR, LUMEN, USERS, expect, signInAs, test } from "./fixtures";

test.setTimeout(120_000);

test("staff can import valid contacts, see errors and duplicates, and track a lead", async ({
  page,
  context,
}) => {
  await signInAs(context, USERS.olivia);
  await page.goto(`${LUMEN}/m/crm/import`);
  await page.getByLabel("Contacts CSV").setInputFiles({
    name: "contacts.csv",
    mimeType: "text/csv",
    buffer: Buffer.from(
      [
        "full_name,email,company,lead_title",
        "CRM Import Test,crm-import@example.test,CRM Test Company,CRM Test Enquiry",
        "Invalid Contact,invalid-email,,",
        "Duplicate Contact,crm-import@example.test,,",
      ].join("\n"),
    ),
  });
  await page.getByRole("button", { name: "Preview CSV" }).click();
  await expect(page.getByRole("status")).toContainText("nothing has been saved");
  await expect(page.getByText(/Row 3, email:/)).toBeVisible();
  await expect(page.getByText(/Row 4: email already used/)).toBeVisible();
  await page.getByRole("button", { name: "Import valid rows" }).click();
  await expect(page.getByRole("status")).toContainText(
    "Imported 1 contacts, 1 customers and 1 leads",
  );
  await page
    .getByRole("navigation", { name: "CRM", exact: true })
    .getByRole("link", { name: "Leads" })
    .click();
  await page.getByRole("link", { name: "CRM Test Enquiry", exact: true }).click();
  await page.getByRole("button", { name: "Mark contacted" }).click();
  await expect(page.getByRole("status")).toContainText("Status updated");
  await expect(page.getByText("Status changed from New to Contacted")).toBeVisible();
  await page.getByRole("button", { name: "Mark lost" }).click();
  await expect(page.getByRole("alert").filter({ hasText: "A reason is required" })).toBeVisible();
  await page.getByLabel("Reason lost").fill("Budget postponed");
  await page.getByRole("button", { name: "Mark lost" }).click();
  await expect(page.getByText("Reason lost: Budget postponed")).toBeVisible();
  await page.getByRole("button", { name: "Reopen" }).click();
  await expect(page.getByText("Status changed from Lost to New")).toBeVisible();
  await page.getByLabel("Add a note").fill("Call next week");
  await page.getByRole("button", { name: "Add note", exact: true }).click();
  await expect(
    page.getByRole("list", { name: "Activity" }).getByText("Call next week"),
  ).toBeVisible();

  // Switching workspace cannot reveal an imported record by its id.
  const leadId = page.url().split("/").at(-1);
  await signInAs(context, USERS.hugo);
  await page.goto(`${HARBOUR}/m/crm/leads/${leadId}`);
  await expect(page.getByRole("heading", { name: "Not found" })).toBeVisible();
});

test("members can create contacts and leads but cannot import or archive", async ({
  page,
  context,
}) => {
  await signInAs(context, USERS.mia);
  await page.goto(`${LUMEN}/m/crm/contacts`);
  await expect(
    page
      .getByRole("navigation", { name: "CRM", exact: true })
      .getByRole("link", { name: "Import" }),
  ).toHaveCount(0);
  await page.getByRole("link", { name: "New contact", exact: true }).click();
  await page.getByLabel("Full name").fill("CRM Member Contact");
  await page.getByLabel("Email", { exact: true }).fill("crm-member@example.test");
  await page.getByRole("button", { name: "Create contact" }).click();
  await expect(page.getByRole("heading", { name: "CRM Member Contact" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Archive contact" })).toHaveCount(0);
  await page.goto(`${LUMEN}/m/crm/leads/new`);
  await page.getByLabel("Contact", { exact: true }).selectOption({ label: "CRM Member Contact" });
  await page.getByLabel("Title", { exact: true }).fill("CRM Member Lead");
  await page.getByRole("button", { name: "Create lead" }).click();
  await expect(page.getByRole("heading", { name: "CRM Member Lead" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Archive lead", exact: true })).toHaveCount(0);
  await page.getByLabel("Title", { exact: true }).fill("CRM Updated Lead");
  await page.getByRole("button", { name: "Save lead" }).click();
  await expect(page.getByRole("heading", { name: "CRM Updated Lead" })).toBeVisible();
  await page.goto(`${LUMEN}/m/crm/import`);
  await expect(page.getByRole("heading", { name: "Not found" })).toBeVisible();
});

test("owners can archive a lead, find its retained history and restore it", async ({
  page,
  context,
}) => {
  await signInAs(context, USERS.olivia);
  await page.goto(`${LUMEN}/m/crm/leads/new`);
  await page.getByLabel("Contact", { exact: true }).selectOption({ label: "Clara Borg" });
  await page.getByLabel("Title", { exact: true }).fill("Archive flow lead");
  await page.getByRole("button", { name: "Create lead", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Archive flow lead", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Archive lead", exact: true }).click();
  await expect(page.getByRole("button", { name: "Restore lead", exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Mark contacted", exact: true })).toHaveCount(0);
  await expect(
    page.getByRole("list", { name: "Activity" }).getByText("Archived", { exact: true }),
  ).toBeVisible();
  await page.getByRole("link", { name: "Back to leads", exact: true }).click();
  await page.getByLabel("Search leads", { exact: true }).fill("Archive flow lead");
  await page.getByRole("button", { name: "Search", exact: true }).click();
  await expect(page.getByRole("link", { name: "Archive flow lead", exact: true })).toHaveCount(0);
  await page.getByLabel("Include archived", { exact: true }).check();
  await page.getByRole("button", { name: "Search", exact: true }).click();
  await page.getByRole("link", { name: "Archive flow lead", exact: true }).click();
  await page.getByRole("button", { name: "Restore lead", exact: true }).click();
  await expect(page.getByRole("button", { name: "Archive lead", exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Mark contacted", exact: true })).toBeVisible();
  await expect(
    page.getByRole("list", { name: "Activity" }).getByText("Restored", { exact: true }),
  ).toBeVisible();
});
