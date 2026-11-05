import { HARBOUR, LUMEN, USERS, expect, signInAs, test } from "./fixtures";

test.setTimeout(120_000);

test("an owner imports lighting SKUs and sees exact prices, VAT, stock and gaps", async ({
  page,
  context,
}) => {
  // Unique codes keep the scenario repeatable against the same e2e database (retries).
  const run = Date.now().toString(36).toUpperCase();
  const product = `E2E-LAMP-${run}`;
  await signInAs(context, USERS.olivia);
  await page.goto(`${LUMEN}/m/catalogue/import`);
  await page.getByLabel("Catalogue CSV").setInputFiles({
    name: "e2e-catalogue.csv",
    mimeType: "text/csv",
    buffer: Buffer.from(
      [
        "sku,product_code,product_name,variant_name,vat_code,price_eur,stock_available,stock_observed_at,attr_wattage",
        `${product}-A,${product},E2E pendant ${run},Brass,STANDARD,129.90,4,2026-11-01T09:00:00+01:00,12`,
        `${product}-B,${product},E2E pendant ${run},Black,STANDARD,,,,12`,
        `${product}-C,${product},E2E pendant ${run},Bad price,STANDARD,12.345,,,`,
        `NOVAT-${run},NOVAT-${run},E2E chandelier ${run},,,,,,`,
      ].join("\n"),
    ),
  });
  await page.getByRole("button", { name: "Preview CSV" }).click();
  await expect(page.getByRole("status")).toContainText("nothing has been saved");
  await expect(page.getByText(/Row 4, price_eur:/)).toBeVisible();
  await page.getByRole("button", { name: "Import valid rows" }).click();
  await expect(page.getByRole("status")).toContainText("Imported 3 new and 0 updated SKUs");

  await page
    .getByRole("navigation", { name: "Catalogue", exact: true })
    .getByRole("link", { name: "Products" })
    .click();
  await page.getByLabel("Search name, code, brand or SKU").fill(`${product}-A`);
  await page.getByRole("button", { name: "Search" }).click();
  await page.getByRole("link", { name: `E2E pendant ${run}`, exact: true }).click();

  const skus = page.getByRole("table", { name: `SKUs of E2E pendant ${run}` });
  const brass = skus.getByRole("row").filter({ hasText: `${product}-A` });
  await expect(brass).toContainText("€129.90");
  await expect(brass).toContainText("incl. VAT");
  await expect(brass).toContainText("In stock");
  await expect(brass).toContainText("main: 4 as of");
  await expect(brass).toContainText("From e2e-catalogue.csv");
  await expect(brass).toContainText("wattage: 12");
  const black = skus.getByRole("row").filter({ hasText: `${product}-B` });
  await expect(black).toContainText("Price not provided");
  await expect(black).toContainText("Stock unknown");
  await expect(page.getByText("Standard rate (test) (STANDARD, 18.00%)")).toBeVisible();

  await page.goto(`${LUMEN}/m/catalogue/products?q=NOVAT-${run}`);
  await expect(page.getByRole("table", { name: "Products" })).toContainText("VAT not set");

  // The import is recorded with its file and changes.
  await page.goto(`${LUMEN}/m/catalogue/imports`);
  await expect(page.getByRole("table", { name: "Catalogue imports" })).toContainText(
    "e2e-catalogue.csv",
  );
});

test("members can browse the catalogue but cannot import or manage it", async ({
  page,
  context,
}) => {
  await signInAs(context, USERS.mia);
  await page.goto(`${LUMEN}/m/catalogue/products`);
  const nav = page.getByRole("navigation", { name: "Catalogue", exact: true });
  await expect(nav.getByRole("link", { name: "Products" })).toBeVisible();
  await expect(nav.getByRole("link", { name: "Import", exact: true })).toHaveCount(0);
  await expect(nav.getByRole("link", { name: "VAT and price lists" })).toHaveCount(0);
  await page.getByRole("link", { name: "Arc pendant light", exact: true }).click();
  const row = page.getByRole("row").filter({ hasText: "ARC-P-30-BRS" });
  await expect(row).toContainText("€129.00");
  await expect(row).toContainText("Entered directly");
  await expect(page.getByRole("button", { name: /Archive/ })).toHaveCount(0);
  await page.goto(`${LUMEN}/m/catalogue/import`);
  await expect(page.getByRole("heading", { name: "Not found" })).toBeVisible();
});

test("a workspace without the catalogue module cannot open it", async ({ page, context }) => {
  await signInAs(context, USERS.hugo);
  await page.goto(`${HARBOUR}/m/catalogue/products`);
  await expect(page.getByRole("heading", { name: "Not found" })).toBeVisible();
});
