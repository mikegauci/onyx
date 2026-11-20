import { LUMEN, USERS, expect, signInAs, test } from "./fixtures";

const SEEDED = "Check the stock count for the brass pendants"; // an admin task in the seed

test("tasks are shown by role and an owner marks one done", async ({ browser }) => {
  // A member does not see tasks meant for admins and owners.
  const member = await browser.newContext();
  await signInAs(member, USERS.mia);
  const memberPage = await member.newPage();
  await memberPage.goto(`${LUMEN}/tasks`);
  await expect(memberPage.getByRole("heading", { name: "Tasks" })).toBeVisible();
  await expect(memberPage.getByText(SEEDED)).toHaveCount(0);

  const owner = await browser.newContext();
  await signInAs(owner, USERS.olivia);
  const page = await owner.newPage();
  await page.goto(LUMEN);
  await page.getByRole("link", { name: /^Tasks \(\d+\)$/ }).click();
  const list = page.getByRole("list", { name: "Open tasks" });
  await expect(list).toContainText(SEEDED);
  await page.getByRole("button", { name: `Mark done: ${SEEDED}` }).click();
  // Closed tasks leave the list (and the row's status message with them).
  await expect(page.getByText(SEEDED)).toHaveCount(0);
  await page.reload();
  await expect(page.getByText(SEEDED)).toHaveCount(0);

  await member.close();
  await owner.close();
});
