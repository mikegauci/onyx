import { LUMEN, USERS, expect, setLumenModule, signInAs, test } from "./fixtures";

// The e2e API uses the in-memory fake email provider: nothing leaves the machine.
test.setTimeout(120_000);

test("an owner sees the email channel's address and sets the sender name", async ({
  page,
  context,
}) => {
  await signInAs(context, USERS.olivia);
  await page.goto(`${LUMEN}/m/inbox/channels`);
  const row = page.getByRole("row").filter({ hasText: "Shop email" });
  await expect(row).toContainText("Active");
  await expect(row).toContainText(/[0-9a-f]{32}@in\.onyx\.test/);
  await expect(row.getByRole("button", { name: /Copy address/ })).toBeVisible();

  const name = `Lumen Lighting ${Date.now().toString(36)}`;
  await page.getByLabel("Sender name", { exact: true }).fill(name);
  await page.getByRole("button", { name: "Save sender details" }).click();
  await expect(page.getByRole("status").filter({ hasText: "Sender details saved" })).toBeVisible();
  await page.reload();
  await expect(page.getByLabel("Sender name", { exact: true })).toHaveValue(name);
});

test.describe("emailed replies", () => {
  test.beforeEach(async () => {
    await setLumenModule("quotations", true);
    await setLumenModule("outbound", true);
  });
  test.afterEach(() => setLumenModule("outbound", false));

  test("an owner approves and sends an email reply in one step", async ({ page, context }) => {
    const subject = `E2E email reply ${Date.now().toString(36)}`;
    await signInAs(context, USERS.olivia);
    await page.goto(`${LUMEN}/m/inbox/conversations/new`);
    await expect(page.getByRole("heading", { name: "New conversation" })).toBeVisible();
    await page.getByLabel("Channel", { exact: true }).selectOption({ label: "Shop email" });
    await page.getByLabel("Subject", { exact: true }).fill(subject);
    await page
      .getByLabel("What the customer said", { exact: true })
      .fill("Is the brass pendant in stock?");
    await page
      .getByLabel("Existing contact", { exact: true })
      .selectOption({ label: "Clara Borg" });
    await page.getByRole("button", { name: "Record conversation" }).click();
    await expect(page.getByRole("heading", { name: subject })).toBeVisible();

    // On email, replies leave only through approval: there is nothing to "log".
    await expect(page.getByRole("radio", { name: "Log a reply" })).toHaveCount(0);
    await expect(page.getByText("To answer the customer by email")).toBeVisible();

    const panel = page.getByRole("region", { name: "Reply for approval" });
    await panel
      .getByLabel("Reply to the customer", { exact: true })
      .fill("Hi Clara, yes, it ships tomorrow.");
    await panel.getByRole("button", { name: "Save for approval" }).click();
    await panel.getByRole("button", { name: "Approve and send" }).click();
    await expect(
      page.getByRole("status").filter({ hasText: "Reply approved and sent" }),
    ).toBeVisible();

    const last = page.getByRole("list", { name: "Messages" }).getByRole("listitem").last();
    await expect(last).toContainText("Hi Clara, yes, it ships tomorrow.");
    await expect(last).toContainText("Emailed to clara.borg@seaview.example.test");
    await expect(last.getByText("Sent", { exact: true })).toBeVisible();
  });
});

test("staff block an address and only an owner can release it", async ({ browser }) => {
  const address = `e2e-${Date.now().toString(36)}@blocked.example.test`;

  const member = await browser.newContext();
  await signInAs(member, USERS.mia);
  const memberPage = await member.newPage();
  await memberPage.goto(`${LUMEN}/m/inbox/suppressions`);
  await expect(memberPage.getByRole("heading", { name: "Blocked addresses" })).toBeVisible();
  await memberPage.getByLabel("Email address", { exact: true }).fill(address);
  await memberPage.getByLabel("Note", { exact: true }).fill("Asked us to stop");
  await memberPage.getByRole("button", { name: "Block address" }).click();
  await expect(memberPage.getByRole("status").filter({ hasText: "Address blocked" })).toBeVisible();
  const memberRow = memberPage.getByRole("row").filter({ hasText: address });
  await expect(memberRow).toContainText("Added by staff");
  // Members cannot release it.
  await expect(memberRow.getByRole("button", { name: /Release/ })).toHaveCount(0);
  await member.close();

  const owner = await browser.newContext();
  await signInAs(owner, USERS.olivia);
  const page = await owner.newPage();
  await page.goto(`${LUMEN}/m/inbox/suppressions`);
  page.once("dialog", (dialog) => void dialog.accept());
  await page.getByRole("button", { name: `Release ${address}` }).click();
  // Released addresses leave the list (the row, and its status message, are removed).
  await expect(page.getByRole("row").filter({ hasText: address })).toHaveCount(0);
  await page.reload();
  await expect(page.getByRole("row").filter({ hasText: address })).toHaveCount(0);
  await owner.close();
});
