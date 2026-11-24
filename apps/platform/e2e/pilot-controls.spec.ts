import { HARBOUR, LUMEN, USERS, expect, signInAs, test } from "./fixtures";

// PR-018: manual mode and the feature switches, on Harbour so other specs keep Lumen as seeded.
test("manual mode shows a banner everywhere and turning it off restores normal service", async ({
  page,
  context,
}) => {
  await signInAs(context, USERS.hugo);
  await page.goto(`${HARBOUR}/settings/pilot`);
  await expect(page.getByRole("heading", { name: "Manual mode", level: 2 })).toBeVisible();

  await page.getByLabel("Reason (optional)").fill("Pilot check");
  await page.getByRole("button", { name: "Turn on manual mode" }).click();
  await expect(
    page.getByRole("status").filter({ hasText: "Manual mode is on." }).first(),
  ).toBeVisible();

  await page.goto(`${HARBOUR}/m/inbox`);
  const banner = page.getByRole("status").filter({ hasText: "Manual mode is on." });
  await expect(banner).toContainText("Reason: Pilot check");

  await banner.getByRole("link", { name: "Pilot controls" }).click();
  await page.getByRole("button", { name: "Turn off manual mode" }).click();
  await expect(
    page.getByRole("status").filter({ hasText: "Manual mode is off." }).first(),
  ).toBeVisible();
  await page.goto(`${HARBOUR}/m/inbox`);
  await expect(page.getByText("Manual mode is on.")).toHaveCount(0);
});

test("feature switches and the baseline are saved", async ({ page, context }) => {
  await signInAs(context, USERS.hugo);
  await page.goto(`${HARBOUR}/settings/pilot`);
  await page.getByLabel("Missed-call text-back").uncheck();
  await page.getByLabel("Typical first reply (minutes)").fill("120");
  await page.getByRole("button", { name: "Save changes" }).click();
  await expect(page.getByRole("status").filter({ hasText: "Pilot controls saved." })).toBeVisible();
  await page.reload();
  await expect(page.getByLabel("Missed-call text-back")).not.toBeChecked();
  await expect(page.getByLabel("Typical first reply (minutes)")).toHaveValue("120");

  await page.goto(`${HARBOUR}/insights`);
  await expect(page.getByText("before Onyx: about 2 h")).toBeVisible();

  // Restore, so a rerun starts from the defaults.
  await page.goto(`${HARBOUR}/settings/pilot`);
  await page.getByLabel("Missed-call text-back").check();
  await page.getByLabel("Typical first reply (minutes)").fill("");
  await page.getByRole("button", { name: "Save changes" }).click();
  await expect(page.getByRole("status").filter({ hasText: "Pilot controls saved." })).toBeVisible();
});

test("members see Insights but not the pilot controls", async ({ page, context }) => {
  await signInAs(context, USERS.mia);
  await page.goto(LUMEN);
  await page.getByRole("link", { name: "Insights" }).first().click();
  await expect(page.getByRole("heading", { name: "Insights", level: 1 })).toBeVisible();
  await expect(page.getByRole("region", { name: "Enquiries by channel" })).toBeVisible();
  await page.getByRole("link", { name: "7 days" }).click();
  await expect(page).toHaveURL(/days=7/);
  await expect(page.getByRole("link", { name: "7 days" })).toHaveAttribute("aria-current", "page");

  await page.goto(`${LUMEN}/settings/pilot`);
  await expect(page.getByRole("heading", { name: "Not found" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Turn on manual mode" })).toHaveCount(0);
});
