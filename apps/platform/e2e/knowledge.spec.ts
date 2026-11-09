import { LUMEN, USERS, expect, lumenAdmin, setLumenModule, signInAs, test } from "./fixtures";

// The e2e API embeds with the deterministic local fake: no provider, no cost.
test.setTimeout(120_000);

test.beforeEach(async () => {
  await setLumenModule("knowledge", true);
  // Indexing is metered like any AI call, so it needs a budget.
  await lumenAdmin("/ai-budget", { monthly_limit_usd_micros: 1_000_000, alert_percent: 80 });
});

test.afterEach(() => setLumenModule("knowledge", false));

test("an owner uploads, searches, replaces and deletes a document", async ({
  page,
  context,
  browser,
}) => {
  const run = Date.now().toString(36);
  const title = `Pendant care ${run}`;
  await signInAs(context, USERS.olivia);
  await page.goto(`${LUMEN}/m/knowledge`);
  await expect(page.getByRole("heading", { name: "Knowledge", level: 1 })).toBeVisible();

  // Upload: the unique run id keeps each file new, since the same file twice is refused.
  await page.getByLabel("Title", { exact: true }).fill(title);
  await page.getByLabel("File", { exact: true }).setInputFiles({
    name: "care.txt",
    mimeType: "text/plain",
    buffer: Buffer.from(
      `Brass pendant care ${run}. Wipe brass fittings with a soft dry cloth.\n\n` +
        "Never use abrasive cleaners or polish on lacquered brass.",
    ),
  });
  await page.getByRole("button", { name: "Upload document" }).click();
  await expect(page.getByRole("heading", { name: title })).toBeVisible();
  await expect(page.getByRole("list", { name: "Passages" })).toContainText("soft dry cloth");
  const documentUrl = page.url();

  // Search cites the document; an unrelated question finds nothing rather than a weak match.
  await page.getByRole("link", { name: "Search" }).click();
  await page.getByLabel("Question", { exact: true }).fill(`how do I clean brass ${run}`);
  await page.getByRole("button", { name: "Search", exact: true }).click();
  const hits = page.getByRole("list", { name: "Matching passages" });
  await expect(hits.getByRole("link", { name: title }).first()).toBeVisible();
  await page.getByLabel("Question", { exact: true }).fill("zebra quantum saxophone");
  await page.getByRole("button", { name: "Search", exact: true }).click();
  await expect(page.getByText("No passage answers this well enough")).toBeVisible();

  // A member reads and searches but cannot change documents.
  const member = await browser.newContext();
  await signInAs(member, USERS.mia);
  const memberPage = await member.newPage();
  await memberPage.goto(documentUrl);
  await expect(memberPage.getByRole("heading", { name: title })).toBeVisible();
  await expect(memberPage.getByRole("button", { name: "Replace file" })).toHaveCount(0);
  await expect(memberPage.getByRole("button", { name: "Delete document" })).toHaveCount(0);
  await memberPage.goto(`${LUMEN}/m/knowledge/documents`);
  await expect(memberPage.getByRole("button", { name: "Upload document" })).toHaveCount(0);
  await member.close();

  // Another tenant's owner gets the not-found page.
  const outsider = await browser.newContext();
  await signInAs(outsider, USERS.hugo);
  const outsiderPage = await outsider.newPage();
  await outsiderPage.goto(documentUrl);
  await expect(outsiderPage.getByRole("heading", { name: title })).toHaveCount(0);
  await outsider.close();

  // Replace the file: a new version.
  await page.goto(documentUrl);
  await page.getByLabel("New file", { exact: true }).setInputFiles({
    name: "care-v2.md",
    mimeType: "text/markdown",
    buffer: Buffer.from(`# Care ${run}\n\nDust brass weekly with a microfibre cloth.`),
  });
  await page.getByRole("button", { name: "Replace file" }).click();
  await expect(page.getByRole("status").filter({ hasText: "version 2" })).toBeVisible();
  await expect(page.getByRole("list", { name: "Passages" })).toContainText("microfibre");

  // Delete, after confirming.
  page.once("dialog", (dialog) => void dialog.accept());
  await page.getByRole("button", { name: "Delete document" }).click();
  await expect(page.getByRole("heading", { name: "Documents", level: 2 })).toBeVisible();
  await expect(page.getByRole("link", { name: title })).toHaveCount(0);
});

test("a file the API cannot read is refused with a reason", async ({ page, context }) => {
  await signInAs(context, USERS.olivia);
  await page.goto(`${LUMEN}/m/knowledge/documents`);
  await page.getByLabel("Title", { exact: true }).fill("Not a PDF");
  await page.getByLabel("File", { exact: true }).setInputFiles({
    name: "fake.pdf",
    mimeType: "application/pdf",
    buffer: Buffer.from("this is not a pdf"),
  });
  await page.getByRole("button", { name: "Upload document" }).click();
  await expect(page.getByRole("alert")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Not a PDF" })).toHaveCount(0);
});
