import { LUMEN, USERS, expect, signInAs, test } from "./fixtures";

// PR-018: the guides are in the app for every member, with a PDF of each.
test("members open the guides and download the PDFs", async ({ page, context }) => {
  await signInAs(context, USERS.mia);
  await page.goto(LUMEN);
  await page.getByRole("link", { name: "Help" }).first().click();
  await expect(page.getByRole("heading", { name: "Guides", level: 1 })).toBeVisible();

  await page.getByRole("link", { name: "Getting started with Onyx", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Getting started with Onyx", level: 1 }),
  ).toBeVisible();
  const contents = page.getByRole("navigation", { name: "On this page" });
  await contents.getByRole("link", { name: /Replies and approvals/ }).click();
  await expect(page).toHaveURL(/#approvals$/);
  await expect(page.getByRole("region", { name: /Replies and approvals/ })).toBeVisible();

  await page.goto(`${LUMEN}/help`);
  await expect(
    page.getByRole("link", { name: "Download PDF for Operator quick reference" }),
  ).toHaveAttribute("href", "/guides/onyx-operator-guide.pdf");
  for (const guide of ["onboarding", "operator"]) {
    const pdf = await page.request.get(`/guides/onyx-${guide}-guide.pdf`);
    expect(pdf.status()).toBe(200);
    expect(pdf.headers()["content-type"]).toContain("application/pdf");
  }
});
