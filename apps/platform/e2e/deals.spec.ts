import { LUMEN, USERS, expect, setLumenModule, signInAs, test } from "./fixtures";

// VA-007 part 1. Files go to the local storage backend; the car comes from the fake Vehica site.
test.setTimeout(180_000);

const JPEG = Buffer.concat([Buffer.from([0xff, 0xd8, 0xff, 0xe0]), Buffer.alloc(256)]);

test.beforeEach(async () => {
  await setLumenModule("catalogue", true);
  await setLumenModule("automotive", true);
  await setLumenModule("deals", true);
});
test.afterEach(async () => {
  await setLumenModule("deals", false);
  await setLumenModule("automotive", false);
});

test("a deal reserves a car, collects documents, and is sold and collected", async ({
  browser,
}) => {
  const owner = await browser.newContext();
  await signInAs(owner, USERS.olivia);
  const page = await owner.newPage();
  await page.goto(`${LUMEN}/m/automotive/import`);
  await page.getByLabel("Website address", { exact: true }).fill("https://dealer.example.test");
  await page.getByRole("button", { name: "Save website" }).click();
  await page.getByRole("button", { name: "Preview import" }).click();
  await page.getByRole("button", { name: "Import these changes" }).click();
  await expect(page.getByRole("status").filter({ hasText: "Imported:" })).toBeVisible();

  // A member creates the deal and uploads a document, but cannot open it.
  const member = await browser.newContext();
  await signInAs(member, USERS.mia);
  const m = await member.newPage();
  await m.goto(`${LUMEN}/m/deals`);
  await m.getByRole("link", { name: "New deal" }).click();
  await m.getByLabel("Customer").selectOption({ label: "Clara Borg" });
  const car = m.getByLabel("Car");
  // The first car in stock (the demo site's titles are "Demo car N").
  const yaris = (await car.locator("option").allTextContents()).find((t) =>
    t.startsWith("Demo car"),
  );
  expect(yaris).toBeTruthy();
  await car.selectOption({ label: yaris! });
  await m.getByRole("button", { name: "Create deal" }).click();
  await expect(m.getByRole("heading", { name: /Clara Borg · / })).toBeVisible();
  await expect(m.getByText("Documents 0 of 3 verified")).toBeVisible();

  await m.getByLabel("Upload ID card or passport").setInputFiles({
    name: "id.jpg",
    mimeType: "image/jpeg",
    buffer: JPEG,
  });
  const checklist = m.getByRole("list", { name: "Checklist" });
  await expect(checklist.getByText("Received, to check")).toBeVisible();
  await expect(m.getByRole("link", { name: /Open .*ID card/ })).toHaveCount(0);
  const dealUrl = m.url();

  // Mark sold is refused while documents are missing.
  await m.getByLabel("Move to").selectOption("sold");
  await m.getByRole("button", { name: "Update stage" }).click();
  await expect(m.getByRole("form", { name: "Change stage" }).getByRole("alert")).toContainText(
    "not verified",
  );

  // The owner checks the document, then overrides for the rest and completes the sale.
  await page.goto(dealUrl);
  await expect(page.getByRole("link", { name: /Open id\.jpg/ })).toBeVisible();
  await page
    .getByRole("form", { name: "Check ID card or passport" })
    .getByRole("button", { name: "Verify" })
    .click();
  await expect(page.getByText("Documents 1 of 3 verified")).toBeVisible();
  await page.getByLabel("Move to").selectOption("sold");
  await page.getByLabel("Reason (for an override)").fill("Licence and address seen in person");
  await page.getByLabel(/Mark it sold even if/).check();
  await page.getByRole("button", { name: "Update stage" }).click();
  await expect(page.getByRole("list", { name: "Deal history" })).toContainText("owner override");
  await page.getByLabel("Move to").selectOption("collected");
  await page.getByRole("button", { name: "Update stage" }).click();
  await expect(page.getByRole("heading", { name: /Clara Borg · / })).toContainText("Collected");

  // The car is sold and no longer offered.
  await page.goto(`${LUMEN}/m/automotive/vehicles?status=available`);
  await expect(page.getByRole("list", { name: "Vehicles" })).not.toContainText(
    yaris!.split(" (")[0]!,
  );

  await owner.close();
  await member.close();
});

test("a customer uploads a document with the link, without signing in", async ({ browser }) => {
  const owner = await browser.newContext();
  await signInAs(owner, USERS.olivia);
  const page = await owner.newPage();
  await page.goto(`${LUMEN}/m/deals/new`);
  await page.getByLabel("Customer").selectOption({ label: "Clara Borg" });
  await page.getByRole("button", { name: "Create deal" }).click();
  await expect(page.getByRole("heading", { name: /Clara Borg/ })).toBeVisible();
  const dealUrl = page.url();

  const request = page.getByRole("form", { name: "Request documents" });
  await request.getByRole("button", { name: "Request documents" }).click();
  const link = await request.getByLabel("Upload link (shown once)").inputValue();
  expect(link).toMatch(/\/u\/[A-Za-z0-9_-]{20,}$/);

  // The customer: a fresh browser with no Onyx session.
  const customer = await browser.newContext();
  const c = await customer.newPage();
  await c.goto(link);
  await expect(c.getByRole("heading", { name: "Upload your documents" })).toBeVisible();
  await expect(c.getByText("Clara")).toHaveCount(0);
  const needed = c.getByRole("list", { name: "Documents needed" });
  await expect(needed.getByRole("listitem")).toHaveCount(3);
  await c.getByLabel("Choose a file for ID card or passport").setInputFiles({
    name: "id.jpg",
    mimeType: "image/jpeg",
    buffer: JPEG,
  });
  await expect(c.getByRole("status")).toContainText("ID card or passport received");
  await expect(needed.getByRole("listitem")).toHaveCount(2);

  await page.goto(dealUrl);
  await expect(page.getByRole("list", { name: "Checklist" })).toContainText("Received, to check");
  await expect(page.getByText(/A link is active until/)).toBeVisible();
  await page.getByRole("button", { name: "Stop this link" }).click();
  await c.reload();
  await expect(c.getByRole("heading", { name: "This link is not valid" })).toBeVisible();

  await owner.close();
  await customer.close();
});
