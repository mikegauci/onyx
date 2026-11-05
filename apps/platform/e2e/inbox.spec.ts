import { HARBOUR, LUMEN, USERS, expect, signInAs, test } from "./fixtures";

test.setTimeout(120_000);

test("a member records a call, assigns it, logs a reply and closes it", async ({
  page,
  context,
}) => {
  // A unique subject keeps the scenario repeatable against the same e2e database (retries).
  const subject = `E2E pendant sizes ${Date.now().toString(36)}`;
  await signInAs(context, USERS.mia);
  await page.goto(`${LUMEN}/m/inbox`);
  await expect(page.getByRole("heading", { name: "Conversations" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Chandelier quote follow-up" })).toBeVisible();

  await page.getByRole("link", { name: "New conversation" }).click();
  // Wait for the form: the list's search box is also labelled with "subject" and "name".
  await expect(page.getByRole("heading", { name: "New conversation" })).toBeVisible();
  await page.getByLabel("Subject", { exact: true }).fill(subject);
  await page
    .getByLabel("What the customer said", { exact: true })
    .fill("Which sizes does the arc pendant come in?");
  await page.getByLabel("Name", { exact: true }).fill("Anna (e2e)");
  await page.getByLabel("Phone", { exact: true }).fill("+356 7900 0456");
  await page.getByRole("button", { name: "Record conversation" }).click();

  await expect(page.getByRole("heading", { name: subject })).toBeVisible();
  const messages = page.getByRole("list", { name: "Messages" });
  await expect(messages).toContainText("Anna (e2e) (customer)");

  await page.getByRole("button", { name: "Assign to me" }).click();
  await expect(
    page.getByRole("status").filter({ hasText: "Assigned to Mia Member" }),
  ).toBeVisible();

  await page
    .getByLabel("Message", { exact: true })
    .fill("Called back: 30 cm and 45 cm, both brass.");
  await page.getByLabel("Then").selectOption("waiting_on_customer");
  await page.getByRole("button", { name: "Log a reply" }).click();
  await expect(messages).toContainText("Reply logged by Mia Member");
  await expect(messages).toContainText("recorded, not sent by Onyx");

  await page.getByRole("button", { name: "Close", exact: true }).click();
  await expect(page.getByRole("list", { name: "History" })).toContainText(
    "Status changed to closed",
  );

  await page.goto(`${LUMEN}/m/inbox/conversations?queue=mine`);
  const row = page.getByRole("row").filter({ hasText: subject });
  await expect(row).toContainText("Closed");
  await expect(row).toContainText("Mia Member");

  // Members cannot manage channels.
  await expect(
    page.getByRole("navigation", { name: "Inbox", exact: true }).getByRole("link", {
      name: "Channels",
    }),
  ).toHaveCount(0);
  await page.goto(`${LUMEN}/m/inbox/channels`);
  await expect(page.getByRole("heading", { name: "Not found" })).toBeVisible();
});

test("another tenant's conversation is not found", async ({ page, context }) => {
  await signInAs(context, USERS.sam);
  await page.goto(`${HARBOUR}/m/inbox/conversations`);
  await expect(page.getByRole("link", { name: "Menu tasting date" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Chandelier quote follow-up" })).toHaveCount(0);
});
