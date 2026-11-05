import { LUMEN, USERS, expect, signInAs, test } from "./fixtures";

test.setTimeout(120_000);

test("an owner drafts a quote, sees a stock warning, approves it and opens the PDF", async ({
  page,
  context,
}) => {
  // A unique title keeps the scenario repeatable against the same e2e database (retries).
  const title = `E2E lobby lights ${Date.now().toString(36)}`;
  await signInAs(context, USERS.olivia);
  await page.goto(`${LUMEN}/m/quotations`);
  await expect(page.getByRole("heading", { name: "Quotes", exact: true })).toBeVisible();
  await page.getByRole("link", { name: "New quote" }).click();
  await expect(page.getByRole("heading", { name: "New quote" })).toBeVisible();
  await page.getByLabel("Title", { exact: true }).fill(title);
  await page.getByLabel("Contact", { exact: true }).selectOption({ label: "Clara Borg" });
  await page.getByRole("button", { name: "Create draft quote" }).click();
  await expect(page.getByRole("heading", { name: new RegExp(title) })).toBeVisible();

  await page.getByLabel("SKU", { exact: true }).fill("ARC-P-30-BRS");
  await page.getByLabel("Quantity", { exact: true }).first().fill("2");
  await page.getByRole("button", { name: "Add SKU" }).click();
  await expect(page.getByTestId("quote-total")).toHaveText("€258.00");

  await page.getByLabel("SKU", { exact: true }).fill("ARC-P-45-BLK");
  await page.getByLabel("Quantity", { exact: true }).first().fill("1");
  await page.getByRole("button", { name: "Add SKU" }).click();
  await expect(page.getByTestId("quote-total")).toHaveText("€427.00");
  await expect(page.getByText("Out of stock.").first()).toBeVisible();

  // The stock warning must be confirmed before approving.
  await page.getByRole("button", { name: "Approve quote" }).click();
  await expect(
    page.getByRole("alert").filter({ hasText: "Confirm the stock warnings" }),
  ).toBeVisible();
  await page.getByRole("checkbox", { name: /Out of stock/ }).check();
  await page.getByRole("button", { name: "Approve quote" }).click();
  await expect(page.getByText("Approved by Olivia Owner")).toBeVisible();

  const pdfLink = page.getByRole("link", { name: "Open PDF preview (version 1)" });
  const pdf = await page.request.get((await pdfLink.getAttribute("href")) ?? "");
  expect(pdf.status()).toBe(200);
  expect(pdf.headers()["content-type"]).toBe("application/pdf");
  expect((await pdf.body()).subarray(0, 5).toString()).toBe("%PDF-");

  await page.getByRole("button", { name: "Revise (new version)" }).click();
  await expect(page.getByText("Version 2 (draft)")).toBeVisible();
  await expect(page.getByRole("link", { name: "Version 1" })).toBeVisible();
});

test("members draft quotes but cannot approve them or change settings", async ({
  page,
  context,
}) => {
  await signInAs(context, USERS.mia);
  await page.goto(`${LUMEN}/m/quotations/quotes`);
  await page.getByRole("link", { name: "Q-2026-0001" }).click();
  await expect(page.getByTestId("quote-total")).toHaveText("€338.00");
  await expect(page.getByRole("button", { name: "Approve quote" })).toHaveCount(0);
  await expect(
    page
      .getByRole("navigation", { name: "Quotations", exact: true })
      .getByRole("link", { name: "Settings" }),
  ).toHaveCount(0);
  await page.goto(`${LUMEN}/m/quotations/settings`);
  await expect(page.getByRole("heading", { name: "Not found" })).toBeVisible();
});
