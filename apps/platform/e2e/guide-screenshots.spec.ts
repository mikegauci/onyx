import { fileURLToPath } from "node:url";

import type { Page } from "@playwright/test";

import { LUMEN, USERS, expect, setLumenModule, signInAs, test } from "./fixtures";

/**
 * Screenshots for the guides (PR-018), from the seeded fake data. Not part of the normal run:
 *   GUIDE_SHOTS=1 pnpm exec playwright test guide-screenshots
 * Then `pnpm guides:pdf` rebuilds the PDFs with them.
 */
test.skip(!process.env.GUIDE_SHOTS, "Set GUIDE_SHOTS=1 to refresh the guide screenshots.");
test.setTimeout(300_000);
test.use({ viewport: { width: 1280, height: 800 }, colorScheme: "light" });

const OUT = fileURLToPath(new URL("../public/guides/", import.meta.url));

async function shot(page: Page, name: string) {
  await page.waitForLoadState("networkidle");
  // Hide the Next.js dev indicator; it is not part of the product.
  await page.addStyleTag({ content: "nextjs-portal { display: none !important; }" });
  await page.screenshot({ path: `${OUT}${name}.png` });
}

test("guide screenshots", async ({ page, context }) => {
  for (const key of ["quotations", "outbound", "automotive", "assistant", "knowledge"]) {
    await setLumenModule(key, true);
  }
  await signInAs(context, USERS.olivia);

  await page.goto(`${LUMEN}/m/automotive/import`);
  await page.getByLabel("Website address", { exact: true }).fill("https://dealer.example.test");
  await page.getByRole("button", { name: "Save website" }).click();
  await page.getByRole("button", { name: "Preview import" }).click();
  await page.getByRole("button", { name: "Import these changes" }).click();
  await expect(page.getByRole("status").filter({ hasText: "Imported:" })).toBeVisible();

  await page.goto(`${LUMEN}/m/inbox/conversations/new`);
  await page.getByLabel("Subject", { exact: true }).fill("Toyota Yaris enquiry");
  await page
    .getByLabel("What the customer said", { exact: true })
    .fill("Hi, is the grey Yaris still available? Could I see it on Saturday morning?");
  await page.getByLabel("Existing contact", { exact: true }).selectOption({ label: "Clara Borg" });
  await page.getByRole("button", { name: "Record conversation" }).click();
  await expect(page.getByRole("heading", { name: "Toyota Yaris enquiry" })).toBeVisible();
  const panel = page.getByRole("region", { name: "Reply for approval" });
  await panel
    .getByLabel("Reply to the customer", { exact: true })
    .fill("Hi Clara, yes, the Yaris is available. Saturday at 10:00 works; see you then!");
  await panel.getByRole("button", { name: "Save for approval" }).click();
  await expect(panel.getByText("Waiting for approval", { exact: true })).toBeVisible();
  await shot(page, "conversation");

  await page.goto(LUMEN);
  await shot(page, "overview");
  await page.goto(`${LUMEN}/m/outbound`);
  await shot(page, "replies");
  await page.goto(`${LUMEN}/m/automotive`);
  await shot(page, "vehicles");
  await page.goto(`${LUMEN}/m/quotations/quotes`);
  await page
    .getByRole("link", { name: /Q-2026-0001/ })
    .first()
    .click();
  await shot(page, "quote");
  await page.goto(`${LUMEN}/insights`);
  await shot(page, "insights");
  await page.goto(`${LUMEN}/settings/pilot`);
  await shot(page, "pilot-controls");

  for (const key of ["automotive", "assistant", "knowledge", "outbound"]) {
    await setLumenModule(key, false);
  }
});
