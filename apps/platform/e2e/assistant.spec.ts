import { LUMEN, USERS, expect, lumenAdmin, setLumenModule, signInAs, test } from "./fixtures";

// The e2e API runs the deterministic fake model: no provider, no cost.
test.setTimeout(120_000);

test.beforeEach(async () => {
  await setLumenModule("assistant", true);
  await lumenAdmin("/ai-budget", { monthly_limit_usd_micros: 1_000_000, alert_percent: 80 });
});

// Off again afterwards: the assistant needs Quotations, which other specs disable.
test.afterEach(() => setLumenModule("assistant", false));

test("staff ask the assistant on a conversation and see why it went to staff", async ({
  page,
  context,
}) => {
  await signInAs(context, USERS.olivia);
  await page.goto(`${LUMEN}/m/inbox`);
  await page.getByRole("link", { name: "Chandelier quote follow-up" }).click();
  await expect(page.getByRole("heading", { name: "Chandelier quote follow-up" })).toBeVisible();

  const panel = page.getByRole("region", { name: "Sales assistant" });
  await panel.getByRole("button", { name: "Draft with assistant" }).click();
  // The fake model proposes no products, so the backend rules hand it to staff.
  await expect(panel.getByRole("status")).toContainText("handed this to staff");
  const runs = panel.getByRole("list", { name: "Recent assistant runs" });
  await expect(runs.getByRole("listitem").first()).toContainText("Handed to staff");
  await expect(runs.getByRole("listitem").first()).toContainText(
    "No products to quote were identified.",
  );

  const messages = page.getByRole("list", { name: "Messages" });
  await expect(messages).toContainText("Internal note by Assistant");
  await expect(messages).toContainText("No quote was drafted");
  // Nothing is sent: the newest message is the note, not a reply.
  await expect(messages.getByRole("listitem").last()).toContainText("Internal note by Assistant");
});

test("the panel and page are gone when the module is off", async ({ page, context }) => {
  await setLumenModule("assistant", false);
  await signInAs(context, USERS.mia);
  await page.goto(`${LUMEN}/m/inbox`);
  await page.getByRole("link", { name: "Chandelier quote follow-up" }).click();
  await expect(page.getByRole("heading", { name: "Chandelier quote follow-up" })).toBeVisible();
  await expect(page.getByRole("region", { name: "Sales assistant" })).toHaveCount(0);
  await expect(page.getByRole("link", { name: "Sales assistant" })).toHaveCount(0);
});

test("owners edit policies and members read them", async ({ browser }) => {
  // A unique topic keeps the scenario repeatable against the same e2e database (retries).
  const topic = `e2e_${Date.now().toString(36)}`;
  const title = `Delivery (${topic})`;

  const owner = await browser.newContext();
  await signInAs(owner, USERS.olivia);
  const page = await owner.newPage();
  await page.goto(`${LUMEN}/m/assistant`);
  await expect(page.getByRole("heading", { name: "Sales assistant", level: 1 })).toBeVisible();

  const add = page.getByRole("region", { name: "Add a policy" });
  await add.getByLabel("Topic").fill(topic);
  await add.getByLabel("Title").fill(title);
  await add.getByLabel("Policy text").fill("Free delivery in Malta on orders over the threshold.");
  await add.getByRole("button", { name: "Add policy" }).click();
  await expect(add.getByRole("status")).toContainText("saved");
  const policies = page.getByRole("list", { name: "Policies" });
  await expect(policies).toContainText(title);

  const member = await browser.newContext();
  await signInAs(member, USERS.mia);
  const memberPage = await member.newPage();
  await memberPage.goto(`${LUMEN}/m/assistant`);
  await expect(memberPage.getByRole("list", { name: "Policies" })).toContainText(title);
  await expect(memberPage.getByRole("region", { name: "Add a policy" })).toHaveCount(0);
  await expect(memberPage.getByText(`Edit ${title}`)).toHaveCount(0);
  await member.close();

  // Clean up, and check deleting works.
  await page.getByText(`Edit ${title}`).click();
  await page.getByRole("button", { name: `Delete policy ${title}` }).click();
  await expect(policies.getByText(title)).toHaveCount(0);
  await owner.close();
});
