import { HARBOUR, LUMEN, USERS, expect, signInAs, test } from "./fixtures";

test.setTimeout(120_000);

// Data protection tools: an owner downloads a person's data and erases it. A fresh contact is
// used so other specs keep the seeded ones.
test("an owner exports and erases a person; members do not see the tools", async ({ browser }) => {
  const name = `Privacy Person ${Date.now().toString(36)}`;
  const owner = await browser.newContext();
  await signInAs(owner, USERS.olivia);
  const page = await owner.newPage();
  await page.goto(`${LUMEN}/m/crm/contacts/new`);
  await page.getByLabel("Full name").fill(name);
  await page.getByLabel("Email", { exact: true }).fill(`${Date.now()}@privacy.example.test`);
  await page.getByRole("button", { name: "Create contact" }).click();
  await expect(page.getByRole("heading", { name })).toBeVisible({ timeout: 45_000 });
  const contactUrl = page.url();

  const exported = await page.request.get(`${new URL(contactUrl).pathname}/export`);
  expect(exported.status()).toBe(200);
  expect((await exported.json()).contact.full_name).toBe(name);

  const member = await browser.newContext();
  await signInAs(member, USERS.mia);
  const m = await member.newPage();
  await m.goto(contactUrl);
  await expect(m.getByRole("heading", { name })).toBeVisible();
  await expect(m.getByRole("region", { name: "Privacy" })).toHaveCount(0);

  const erase = page.getByRole("form", { name: "Erase this person" });
  await erase.getByLabel(/Type .* to confirm/).fill("wrong name");
  await erase.getByRole("button", { name: "Erase this person" }).click();
  await expect(erase.getByRole("alert")).toContainText("full name");
  await erase.getByLabel(/Type .* to confirm/).fill(name);
  await erase.getByRole("button", { name: "Erase this person" }).click();
  await expect(page.getByRole("heading", { name: "Erased contact" })).toBeVisible();
  await expect(page.getByText("This person’s data was erased.")).toBeVisible();

  await owner.close();
  await member.close();
});

test("owners set conversation retention; admins do not see it", async ({ browser }) => {
  const owner = await browser.newContext();
  await signInAs(owner, USERS.olivia);
  const page = await owner.newPage();
  await page.goto(`${LUMEN}/settings/privacy`);
  await page.getByLabel("Remove conversations after").selectOption("12");
  await page.getByRole("button", { name: "Save" }).click();
  await expect(page.getByRole("status").filter({ hasText: "12 months" })).toBeVisible();
  await page.reload();
  await expect(page.getByLabel("Remove conversations after")).toHaveValue("12");
  // Back to the default, so other specs see every conversation.
  await page.getByLabel("Remove conversations after").selectOption("");
  await page.getByRole("button", { name: "Save" }).click();
  await expect(page.getByRole("status").filter({ hasText: "kept" })).toBeVisible();

  const admin = await browser.newContext();
  await signInAs(admin, USERS.sam);
  const a = await admin.newPage();
  await a.goto(`${HARBOUR}/settings/general`); // Sam is a Harbour admin
  await expect(
    a.getByRole("navigation", { name: "Settings" }).getByRole("link", { name: "Privacy" }),
  ).toHaveCount(0);
  await owner.close();
  await admin.close();
});
