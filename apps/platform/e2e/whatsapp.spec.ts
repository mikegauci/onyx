import { createHmac } from "node:crypto";

import { E2E, WHATSAPP_E2E_SECRET } from "../playwright.config";
import { LUMEN, USERS, expect, setLumenModule, signInAs, test } from "./fixtures";

// The e2e API uses the in-memory fake WhatsApp provider: nothing reaches Meta.
test.setTimeout(120_000);

const NUMBER_ID = "100000000000009"; // the seeded "WhatsApp" channel's business number

function randomNumber(): string {
  return `35679${Math.floor(Math.random() * 1_000_000)
    .toString()
    .padStart(6, "0")}`;
}

/** Deliver a customer message the way Meta does: a webhook signed with the app secret. */
async function receive(from: string, name: string, body: string) {
  const payload = JSON.stringify({
    object: "whatsapp_business_account",
    entry: [
      {
        id: "200000000000009",
        changes: [
          {
            field: "messages",
            value: {
              messaging_product: "whatsapp",
              metadata: { display_phone_number: "35621000009", phone_number_id: NUMBER_ID },
              contacts: [{ profile: { name }, wa_id: from }],
              messages: [
                {
                  from,
                  id: `wamid.e2e-${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`,
                  timestamp: Math.floor(Date.now() / 1000).toString(),
                  type: "text",
                  text: { body },
                },
              ],
            },
          },
        ],
      },
    ],
  });
  const signature = createHmac("sha256", WHATSAPP_E2E_SECRET).update(payload).digest("hex");
  const response = await fetch(`${E2E.apiUrl}/v1/webhooks/whatsapp`, {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-Hub-Signature-256": `sha256=${signature}` },
    body: payload,
  });
  expect(response.status).toBe(200);
}

test("an owner sees the business number and refreshes its templates", async ({ page, context }) => {
  await signInAs(context, USERS.olivia);
  await page.goto(`${LUMEN}/m/inbox/channels`);
  const row = page.getByRole("row").filter({ hasText: "+356 2100 0009" });
  await expect(row).toContainText("Active");
  await page.getByRole("button", { name: "Refresh templates for WhatsApp from WhatsApp" }).click();
  await expect(page.getByRole("status").filter({ hasText: "Templates refreshed" })).toBeVisible();
  const templates = page.getByRole("table", { name: "Templates for WhatsApp" });
  await expect(templates.getByRole("row").filter({ hasText: "follow_up" })).toContainText("Yes");
});

test.describe("WhatsApp replies", () => {
  test.beforeEach(() => setLumenModule("outbound", true));
  test.afterEach(() => setLumenModule("outbound", false));

  test("a customer message opens the window and an approved text reply is sent", async ({
    page,
    context,
  }) => {
    const tag = Date.now().toString(36);
    const body = `E2E wa ${tag} is the Golf in?`;
    await receive(randomNumber(), `E2E Customer ${tag}`, body);

    await signInAs(context, USERS.olivia);
    await page.goto(`${LUMEN}/m/inbox/conversations?queue=all`);
    await page.getByRole("link", { name: body }).click();
    await expect(page.getByRole("note").filter({ hasText: "free-text reply until" })).toBeVisible();
    // Replies leave only through approval: there is nothing to "log".
    await expect(page.getByRole("radio", { name: "Log a reply" })).toHaveCount(0);

    const panel = page.getByRole("region", { name: "Reply for approval" });
    await expect(panel.getByRole("radio", { name: "Text message" })).toBeChecked();
    await panel.getByLabel("Reply to the customer", { exact: true }).fill("Yes, it is in.");
    await panel.getByRole("button", { name: "Save for approval" }).click();
    await panel.getByRole("button", { name: "Approve and send" }).click();
    await expect(
      page.getByRole("status").filter({ hasText: "Reply approved and sent" }),
    ).toBeVisible();

    const last = page.getByRole("list", { name: "Messages" }).getByRole("listitem").last();
    await expect(last).toContainText("Yes, it is in.");
    await expect(last).toContainText("WhatsApp to +35679");
    await expect(last.getByText("Sent", { exact: true })).toBeVisible();
  });

  test("after the window closes only a template can be sent", async ({ page, context }) => {
    const tag = Date.now().toString(36);
    const subject = `E2E wa template ${tag}`;
    // The templates must be in Onyx before the picker can offer them.
    await signInAs(context, USERS.olivia);
    await page.goto(`${LUMEN}/m/inbox/channels`);
    await page
      .getByRole("button", { name: "Refresh templates for WhatsApp from WhatsApp" })
      .click();
    await expect(page.getByRole("status").filter({ hasText: "Templates refreshed" })).toBeVisible();

    // Recorded by staff, so no WhatsApp message from the customer opened a window.
    await page.goto(`${LUMEN}/m/inbox/conversations/new`);
    await page.getByLabel("Channel", { exact: true }).selectOption({ label: "WhatsApp" });
    await page.getByLabel("Subject", { exact: true }).fill(subject);
    await page
      .getByLabel("What the customer said", { exact: true })
      .fill("Asked yesterday about the Golf.");
    await page.getByLabel("Name", { exact: true }).fill(`Walk-in ${tag}`);
    await page.getByLabel("Phone", { exact: true }).fill(`+${randomNumber()}`);
    await page.getByRole("button", { name: "Record conversation" }).click();
    await expect(page.getByRole("heading", { name: subject })).toBeVisible();
    await expect(page.getByRole("note").filter({ hasText: "window is closed" })).toBeVisible();

    const panel = page.getByRole("region", { name: "Reply for approval" });
    await expect(panel.getByRole("radio", { name: "Text message" })).toBeDisabled();
    await expect(panel.getByRole("radio", { name: "Approved template" })).toBeChecked();
    await panel.getByLabel("Value {{1}}", { exact: true }).fill("Clara");
    await expect(panel.getByLabel("Template preview")).toContainText("Hello Clara");
    await panel.getByRole("button", { name: "Save for approval" }).click();
    await panel.getByRole("button", { name: "Approve and send" }).click();
    await expect(
      page.getByRole("status").filter({ hasText: "Reply approved and sent" }),
    ).toBeVisible();

    const last = page.getByRole("list", { name: "Messages" }).getByRole("listitem").last();
    await expect(last).toContainText("Hello Clara");
    await expect(last).toContainText("template follow_up");
  });
});

test("a customer who replies STOP is blocked", async ({ page, context }) => {
  const from = randomNumber();
  await receive(from, "E2E Stopper", "STOP");
  await signInAs(context, USERS.olivia);
  await page.goto(`${LUMEN}/m/inbox/suppressions`);
  const row = page.getByRole("row").filter({ hasText: `+${from}` });
  await expect(row).toContainText("Opted out on WhatsApp");
});
