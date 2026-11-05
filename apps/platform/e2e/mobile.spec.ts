import { LUMEN, USERS, expect, signInAs, test } from "./fixtures";

test("navigation collapses into a sheet on small screens", async ({ page, context }) => {
  await signInAs(context, USERS.olivia);
  await page.goto(LUMEN);
  await expect(
    page.getByRole("heading", { level: 1, name: "Lumen Lighting (test)" }),
  ).toBeVisible();
  const nav = page.getByRole("navigation", { name: "Workspace" });
  await expect(nav).toBeHidden();

  await page.getByRole("button", { name: "Toggle navigation" }).click();
  const sheet = page.getByRole("dialog");
  await expect(sheet.getByRole("link", { name: "Settings" })).toBeVisible();
  await sheet.getByRole("link", { name: "Settings" }).click();
  await expect(page).toHaveURL(`${LUMEN}/settings/general`);

  const width = await page.evaluate(() => document.documentElement.scrollWidth);
  const viewport = page.viewportSize()!.width;
  expect(width).toBeLessThanOrEqual(viewport);
});
