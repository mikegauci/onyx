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
  // The seeded tenants (onboarding tests may add more in the same run).
  await expect(table.getByText("lumen-lighting-test")).toBeVisible();
  await expect(table.getByText("harbour-catering-test")).toBeVisible();

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

test("platform admin connects a WhatsApp number and a phone line from the admin screens", async ({
  page,
  context,
}) => {
  const digits = (n: number) =>
    Math.floor(Math.random() * 10 ** n)
      .toString()
      .padStart(n, "0");
  const line = `+35627${digits(6)}`;
  await signInAs(context, USERS.pat);
  await page.goto("/admin/organizations/harbour-catering-test");

  const whatsapp = page.getByRole("form", { name: "Connect a WhatsApp number" });
  await whatsapp.getByLabel("Phone number", { exact: true }).fill("+356 2100 7777");
  await whatsapp.getByLabel("Channel name").fill("Harbour WhatsApp");
  await whatsapp.getByLabel("Phone number ID").fill(`1${digits(14)}`);
  await whatsapp.getByLabel("WhatsApp Business account ID").fill(`2${digits(14)}`);
  await whatsapp.getByRole("button", { name: "Connect WhatsApp number" }).click();
  await expect(whatsapp.getByRole("status")).toContainText("WhatsApp number connected");
  await expect(page.getByRole("list", { name: "Channels" })).toContainText("+356 2100 7777");

  const phone = page.getByRole("form", { name: "Connect a phone line" });
  await phone.getByLabel("Cloud number").fill(line);
  await phone.getByLabel("WhatsApp channel").selectOption("Harbour WhatsApp");
  await phone.getByRole("button", { name: "Connect phone line" }).click();
  await expect(phone.getByRole("status")).toContainText(`Phone line ${line} connected`);
  await expect(page.getByRole("list", { name: "Phone lines" })).toContainText(line);

  // The same number cannot be connected twice.
  await phone.getByLabel("Cloud number").fill(line);
  await phone.getByRole("button", { name: "Connect phone line" }).click();
  await expect(phone.getByRole("alert")).toContainText("already connected");
});
