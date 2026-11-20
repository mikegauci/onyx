import { LUMEN, USERS, expect, setLumenModule, signInAs, test } from "./fixtures";

// The e2e API imports from a built-in demo Vehica site: nothing reaches the internet.
test.setTimeout(120_000);

test.describe("vehicles", () => {
  test.beforeEach(() => setLumenModule("automotive", true));
  test.afterEach(() => setLumenModule("automotive", false));

  test("an owner connects the website, previews, imports, and staff browse the stock", async ({
    browser,
  }) => {
    const owner = await browser.newContext();
    await signInAs(owner, USERS.olivia);
    const page = await owner.newPage();
    await page.goto(`${LUMEN}/m/automotive/import`);
    await page.getByLabel("Website address", { exact: true }).fill("https://dealer.example.test");
    await page.getByRole("button", { name: "Save website" }).click();
    await expect(page.getByRole("status").filter({ hasText: "Website saved" })).toBeVisible();

    await page.getByRole("button", { name: "Preview import" }).click();
    await expect(page.getByText(/4 listings on the site/)).toBeVisible();
    await page.getByRole("button", { name: "Import these changes" }).click();
    await expect(page.getByRole("status").filter({ hasText: "Imported:" })).toBeVisible();

    // Importing again changes nothing.
    await page.reload();
    await page.getByRole("button", { name: "Preview import" }).click();
    await expect(page.getByText(/0 new, 0 changed, 4 unchanged/)).toBeVisible();

    // A member browses the stock but cannot import.
    const member = await browser.newContext();
    await signInAs(member, USERS.mia);
    const memberPage = await member.newPage();
    await memberPage.goto(`${LUMEN}/m/automotive`);
    const cars = memberPage.getByRole("list", { name: "Vehicles" }).getByRole("listitem");
    await expect(cars).toHaveCount(4);
    await expect(memberPage.getByRole("link", { name: "Import from website" })).toHaveCount(0);
    await memberPage.getByLabel("Search", { exact: true }).fill("Yaris");
    await memberPage.getByRole("button", { name: "Show" }).click();
    await expect(cars).toHaveCount(2);
    await cars.first().getByRole("link").click();
    await expect(memberPage.getByRole("link", { name: "View on the website" })).toBeVisible();
    await expect(memberPage.getByText(/€16,500.00|Price on request/)).toBeVisible();

    await owner.close();
    await member.close();
  });

  test("an address that is not a public https site is refused", async ({ page, context }) => {
    await signInAs(context, USERS.olivia);
    await page.goto(`${LUMEN}/m/automotive/import`);
    await page.getByLabel("Website address", { exact: true }).fill("http://dealer.example.test");
    await page.getByRole("button", { name: "Save website" }).click();
    await expect(page.getByRole("alert").filter({ hasText: "https address" })).toBeVisible();
  });
});
