import { createHmac } from "node:crypto";

import { E2E, TELEPHONY_E2E_SECRET } from "../playwright.config";
import { LUMEN, USERS, expect, signInAs, test } from "./fixtures";

// VA-004: the e2e API uses fake telephony and WhatsApp providers; nothing leaves the machine.
test.setTimeout(120_000);

function digits(n: number): string {
  return Math.floor(Math.random() * 10 ** n)
    .toString()
    .padStart(n, "0");
}

async function connectLine(number: string) {
  const session = await (
    await fetch(`${E2E.authUrl}/__e2e/session?email=${encodeURIComponent(USERS.pat)}`)
  ).json();
  const response = await fetch(
    `${E2E.apiUrl}/v1/admin/organizations/lumen-lighting-test/phone-lines`,
    {
      method: "POST",
      headers: {
        Authorization: `Bearer ${session.access_token}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ number, whatsapp_channel_name: "WhatsApp" }),
    },
  );
  expect(response.status).toBe(200);
}

/** A forwarded call, as the provider reports it: a webhook signed with the shared secret. */
async function missedCall(from: string, to: string, callId: string) {
  const body = JSON.stringify({ call_id: callId, from, to });
  const signature = createHmac("sha256", TELEPHONY_E2E_SECRET).update(body).digest("hex");
  const response = await fetch(`${E2E.apiUrl}/v1/webhooks/telephony`, {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-Onyx-Fake-Signature": signature },
    body,
  });
  expect(response.status).toBe(200);
}

test("a missed call reaches the inbox once, with a task and one automatic text-back", async ({
  page,
  context,
}) => {
  const line = `+35627${digits(6)}`;
  const caller = `+35679${digits(6)}`;
  await connectLine(line);

  await signInAs(context, USERS.olivia);
  await page.goto(`${LUMEN}/m/inbox/channels`);
  await page.getByRole("button", { name: "Refresh templates for WhatsApp from WhatsApp" }).click();
  await expect(page.getByRole("status").filter({ hasText: "Templates refreshed" })).toBeVisible();

  const settings = page.getByRole("region", { name: "Missed-call text-back" });
  await expect(settings).toContainText(line);
  await settings.getByLabel("Send the caller a message automatically").check();
  await settings
    .getByLabel("WhatsApp template", { exact: true })
    .selectOption({ label: "follow_up (en)" });
  await settings.getByLabel("Value {{1}}", { exact: true }).fill("there");
  await expect(settings.getByLabel("Template preview")).toContainText("Hello there");
  await settings.getByRole("button", { name: "Save text-back settings" }).click();
  await expect(
    page.getByRole("status").filter({ hasText: "Text-back settings saved" }),
  ).toBeVisible();

  const callId = `CA-e2e-${Date.now().toString(36)}`;
  await missedCall(caller, line, callId);
  await missedCall(caller, line, callId); // the provider retries: nothing new

  await page.goto(`${LUMEN}/m/inbox/conversations`);
  await page.getByRole("link", { name: `Missed call from ${caller}` }).click();
  const messages = page.getByRole("list", { name: "Messages" });
  await expect(messages.getByRole("listitem")).toHaveCount(2);
  await expect(messages.getByRole("listitem").first()).toContainText("Missed call");
  await expect(messages.getByRole("listitem").last()).toContainText(
    "Automatic message (missed-call text-back)",
  );

  await page.goto(`${LUMEN}/tasks`);
  await expect(page.getByRole("list", { name: "Open tasks" })).toContainText(`Call back ${caller}`);
});
