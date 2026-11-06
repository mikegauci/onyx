import type { Page } from "@playwright/test";

import { LUMEN, USERS, expect, setLumenModule, signInAs, test } from "./fixtures";

test.setTimeout(120_000);

test.beforeEach(async () => {
  // Outbound replies need Inbox and Quotations; other specs may have turned Quotations off.
  await setLumenModule("quotations", true);
  await setLumenModule("outbound", true);
});

// Off again afterwards: outbound needs Quotations, which other specs disable.
test.afterEach(() => setLumenModule("outbound", false));

/** Record a new conversation with Clara Borg. A unique subject keeps retries independent. */
async function newConversation(page: Page, subject: string) {
  await page.goto(`${LUMEN}/m/inbox/conversations/new`);
  await expect(page.getByRole("heading", { name: "New conversation" })).toBeVisible();
  await page.getByLabel("Subject", { exact: true }).fill(subject);
  await page
    .getByLabel("What the customer said", { exact: true })
    .fill("Could you send the chandelier quote over?");
  await page.getByLabel("Existing contact", { exact: true }).selectOption({ label: "Clara Borg" });
  await page.getByRole("button", { name: "Record conversation" }).click();
  await expect(page.getByRole("heading", { name: subject })).toBeVisible();
}

test("a member drafts a reply, an owner edits and approves it, and it is sent", async ({
  browser,
}) => {
  const subject = `E2E reply approval ${Date.now().toString(36)}`;
  const reply = "Hi Clara, the chandelier is in stock and we can deliver next week.";

  const member = await browser.newContext();
  await signInAs(member, USERS.mia);
  const memberPage = await member.newPage();
  await newConversation(memberPage, subject);

  const panel = memberPage.getByRole("region", { name: "Reply for approval" });
  await panel.getByLabel("Reply to the customer", { exact: true }).fill(reply);
  await panel.getByRole("button", { name: "Save for approval" }).click();
  await expect(panel.getByText("Waiting for approval", { exact: true })).toBeVisible();
  // A member cannot approve or send it.
  await expect(panel.getByRole("button", { name: /Approve/ })).toHaveCount(0);
  await expect(panel.getByRole("button", { name: "Send reply" })).toHaveCount(0);
  await expect(panel).toContainText("An admin or owner must approve this reply");
  await member.close();

  const owner = await browser.newContext();
  await signInAs(owner, USERS.olivia);
  const page = await owner.newPage();
  await page.goto(`${LUMEN}/m/outbound`);
  await expect(page.getByRole("heading", { name: "Outbound replies", level: 1 })).toBeVisible();
  await page
    .getByRole("list", { name: "Waiting for approval" })
    .getByRole("link", { name: subject })
    .click();
  await expect(page.getByRole("heading", { name: `Reply: ${subject}` })).toBeVisible();

  const text = page.getByLabel("Reply text", { exact: true });
  await expect(text).toHaveValue(reply);
  await text.fill(`${reply} Kind regards, Lumen.`);
  await page.getByRole("button", { name: "Approve edited text" }).click();
  await expect(page.getByRole("status").filter({ hasText: "approved" })).toBeVisible();
  await expect(page.getByText("Approved, not sent", { exact: true })).toBeVisible();

  // Both revisions stay on record.
  await page.getByText("All revisions (2)").click();
  const revisions = page.getByRole("list", { name: "Revisions" });
  await expect(revisions.getByRole("listitem")).toHaveCount(2);
  await expect(revisions.getByRole("listitem").first()).toContainText("Mia Member");

  await page.getByRole("button", { name: "Send reply" }).click();
  await expect(page.getByRole("status").filter({ hasText: "Reply sent" })).toBeVisible();
  await expect(page.getByText("Sent by Olivia Owner")).toBeVisible();

  await page.getByRole("link", { name: `Conversation: ${subject}` }).click();
  const messages = page.getByRole("list", { name: "Messages" });
  await expect(messages.getByRole("listitem").last()).toContainText("Kind regards, Lumen.");
  await expect(messages.getByRole("listitem").last()).toContainText("Olivia Owner");
  await owner.close();
});

test("a reply with a draft quote cannot be approved or sent", async ({ page, context }) => {
  const stamp = Date.now().toString(36);
  const title = `E2E outbound quote ${stamp}`;
  const subject = `E2E quote reply ${stamp}`;
  await signInAs(context, USERS.olivia);

  // A draft quote for Clara, not approved.
  await page.goto(`${LUMEN}/m/quotations/quotes/new`);
  await expect(page.getByRole("heading", { name: "New quote" })).toBeVisible();
  await page.getByLabel("Title", { exact: true }).fill(title);
  await page.getByLabel("Contact", { exact: true }).selectOption({ label: "Clara Borg" });
  await page.getByRole("button", { name: "Create draft quote" }).click();
  await expect(page.getByRole("heading", { name: new RegExp(title) })).toBeVisible();

  await newConversation(page, subject);
  const panel = page.getByRole("region", { name: "Reply for approval" });
  await panel
    .getByLabel("Reply to the customer", { exact: true })
    .fill("Hi Clara, your quote is attached.");
  const option = panel.locator("option", { hasText: title });
  await panel
    .getByLabel("Include quote", { exact: true })
    .selectOption((await option.getAttribute("value")) ?? "");
  await panel.getByRole("button", { name: "Save for approval" }).click();
  await expect(panel.getByText("Waiting for approval", { exact: true })).toBeVisible();

  // Even the owner cannot approve it until the quote is approved, and nothing can be sent.
  await expect(panel).toContainText("Approve the quote before approving a reply");
  await expect(panel.getByRole("button", { name: /Approve/ })).toHaveCount(0);
  await expect(panel.getByRole("button", { name: "Send reply" })).toHaveCount(0);
  const messages = page.getByRole("list", { name: "Messages" });
  await expect(messages.getByRole("listitem")).toHaveCount(1); // the customer's message only
});
