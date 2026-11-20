import { USERS, expect, signInAs, test } from "./fixtures";

test.setTimeout(120_000);

test("a platform admin onboards a tenant, its owner brands it, and suspension locks it", async ({
  browser,
}) => {
  const tag = Date.now().toString(36);
  const name = `Ventur E2E ${tag}`;
  const slug = `ventur-e2e-${tag}`;
  const ownerEmail = `owner-${tag}@ventur.example.test`;

  // The admin creates the organisation and gets the owner's one-time link.
  const admin = await browser.newContext();
  await signInAs(admin, USERS.pat);
  const adminPage = await admin.newPage();
  await adminPage.goto("/admin");
  await adminPage.getByRole("link", { name: "New organisation" }).click();
  await adminPage.getByLabel("Organisation name", { exact: true }).fill(name);
  await expect(adminPage.getByLabel("Address", { exact: true })).toHaveValue(slug);
  await adminPage.getByLabel("Owner's email", { exact: true }).fill(ownerEmail);
  const modules = adminPage.getByRole("group", { name: "Modules" });
  await modules.getByRole("checkbox", { name: /^Quotations/ }).check();
  // Quotations needs the catalogue, which is ticked for it.
  await expect(modules.getByRole("checkbox", { name: /^Product catalogue/ })).toBeChecked();
  await adminPage.getByRole("button", { name: "Create organisation" }).click();
  await expect(adminPage.getByRole("status").filter({ hasText: `${name} created` })).toBeVisible();
  const link = await adminPage.getByLabel("Owner's one-time invitation link").inputValue();
  expect(link).toContain("/invitations/accept?token=");

  // The owner accepts and sets a brand colour.
  const owner = await browser.newContext();
  await signInAs(owner, ownerEmail);
  const ownerPage = await owner.newPage();
  await ownerPage.goto(new URL(link).pathname + new URL(link).search);
  await ownerPage.getByRole("button", { name: /Accept/ }).click();
  await expect(ownerPage).toHaveURL(new RegExp(`/w/${slug}`));
  await ownerPage.goto(`/w/${slug}/settings/general`);
  await ownerPage.getByLabel("Brand colour", { exact: true }).fill("#ffff00");
  await expect(ownerPage.getByText(/too light/)).toBeVisible();
  await ownerPage.getByLabel("Brand colour", { exact: true }).fill("#1f4e79");
  await ownerPage.getByLabel("Display name", { exact: true }).fill("Ventur");
  await ownerPage.getByRole("button", { name: "Save changes" }).click();
  await expect(
    ownerPage.getByRole("status").filter({ hasText: "Workspace settings saved" }),
  ).toBeVisible();
  await ownerPage.reload();
  await expect(
    ownerPage.getByRole("button", { name: /Switch workspace \(current: Ventur\)/ }),
  ).toBeVisible();

  // The admin suspends it: the owner sees why. Then reactivates it.
  await adminPage.goto(`/admin/organizations/${slug}`);
  adminPage.once("dialog", (dialog) => void dialog.accept());
  await adminPage.getByRole("button", { name: "Suspend organisation" }).click();
  const heading = adminPage.getByRole("heading", { level: 1 });
  await expect(heading).toContainText("Suspended");
  await ownerPage.goto(`/w/${slug}`);
  await expect(
    ownerPage.getByRole("heading", { name: "This workspace is suspended" }),
  ).toBeVisible();

  await adminPage.getByRole("button", { name: "Reactivate" }).click();
  await expect(heading).toContainText("Active");
  await ownerPage.goto(`/w/${slug}`);
  await expect(ownerPage.getByRole("heading", { name: "This workspace is suspended" })).toHaveCount(
    0,
  );
  await expect(adminPage.getByRole("list", { name: "Invitations" })).toContainText("Accepted");

  await admin.close();
  await owner.close();
});
