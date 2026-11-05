import { LUMEN, USERS, expect, signInAs, test } from "./fixtures";

test("platform admin sees account metadata in the admin shell", async ({ page, context }) => {
  await signInAs(context, USERS.pat);
  await page.goto("/workspaces");
  await page.getByRole("link", { name: "Open platform admin" }).click();
  await expect(page).toHaveURL("/admin");
  await expect(
    page.getByRole("status").getByText(/Platform admin · account metadata only/),
  ).toBeVisible();
  const table = page.getByRole("table", { name: "Organisations" });
  await expect(table.getByRole("row")).toHaveCount(3); // header + 2 tenants
  await expect(table.getByText("lumen-lighting-test")).toBeVisible();

  await page
    .getByRole("navigation", { name: "Platform admin" })
    .getByRole("link", { name: "API status" })
    .click();
  await expect(page.getByRole("heading", { name: "API status" })).toBeVisible();
});

test("platform admin has no tenant access", async ({ page, context }) => {
  await signInAs(context, USERS.pat);
  await page.goto(LUMEN);
  await expect(page.getByRole("heading", { name: "Not found" })).toBeVisible();
});

for (const who of ["olivia", "sam", "hugo"] as const) {
  test(`tenant user ${who} cannot open the admin shell`, async ({ page, context }) => {
    await signInAs(context, USERS[who]);
    await page.goto("/admin");
    await expect(page.getByRole("heading", { name: "Not found" })).toBeVisible();
    await expect(page.getByText(/Platform admin ·/)).toHaveCount(0);
  });
}
