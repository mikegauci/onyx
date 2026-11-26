import { LUMEN, USERS, expect, signInAs, test } from "./fixtures";

// VA-010: an owner sees today's summary so far, with missing sources shown as missing, and
// chooses who gets it.
test.setTimeout(120_000);

test("an owner previews the daily summary and chooses who gets it", async ({ page, context }) => {
  await signInAs(context, USERS.olivia);
  await page.goto(`${LUMEN}/insights`);
  await page.getByRole("link", { name: /Daily summary by email or WhatsApp/ }).click();
  await expect(page.getByRole("heading", { name: "Daily summary" })).toBeVisible({
    timeout: 30_000,
  });
  await expect(page.getByText("Facebook/Instagram: not connected")).toBeVisible();

  const olivia = page.getByRole("checkbox", { name: /Olivia Owner/ });
  await page.getByLabel("Send the daily summary").check();
  await olivia.check();
  await page.getByLabel("Send at").fill("18:30");
  await page.getByRole("button", { name: "Save" }).click();
  await expect(page.getByText("Saved.")).toBeVisible({ timeout: 30_000 });

  await page.reload();
  await expect(page.getByLabel("Send the daily summary")).toBeChecked();
  await expect(olivia).toBeChecked();
  await expect(page.getByLabel("Send at")).toHaveValue("18:30");

  await page.getByLabel("Send the daily summary").uncheck();
  await page.getByRole("button", { name: "Save" }).click();
  await expect(page.getByText("Saved.")).toBeVisible({ timeout: 30_000 });
});
