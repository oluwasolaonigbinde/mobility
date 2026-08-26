import { expect, test, type Page } from "@playwright/test";

const ADVERTISER = {
  email: "advertiser@demo.mobility.local",
  password: "DemoAdvertiser12345!",
};
const ADMIN = {
  email: "admin@demo.mobility.local",
  password: "DemoAdmin12345!",
};

async function login(page: Page, credentials: typeof ADVERTISER, destination: string) {
  await page.context().clearCookies();
  await page.goto("/login");
  await page.getByLabel("Email").fill(credentials.email);
  await page.getByLabel("Password").fill(credentials.password);
  await page.getByRole("button", { name: "Enter the network" }).click();
  await page.waitForURL(`**/${destination}`);
}

test("advertiser preview and reasoned admin decision complete a mid-flight change", async ({
  page,
}) => {
  test.setTimeout(60_000);
  const reductionReason = `Synthetic governed reduction ${Date.now()}`;
  const decisionReason = "Approved synthetic reduction with accepted driver terms preserved";

  await login(page, ADVERTISER, "advertiser");
  await page.goto("/advertiser/campaigns");
  await page.getByRole("link", { name: "Demo Lagos Mobility Campaign" }).click();
  await expect(page.getByRole("heading", { name: "Campaign changes" })).toBeVisible();

  await page.getByLabel("Total budget").fill("999999999.00");
  await page.getByLabel("Reason", { exact: true }).fill("Synthetic funded-scope expansion");
  await page.getByRole("button", { name: "Preview and request change" }).click();
  await expect(page.getByText("✓ Campaign change recorded.")).toBeVisible();
  await expect(page.getByText("applied", { exact: true }).first()).toBeVisible();

  await page.getByLabel("Total budget").fill("999999998.00");
  await page.getByLabel("Reason", { exact: true }).fill(reductionReason);
  await page.getByRole("button", { name: "Preview and request change" }).click();
  await expect(page.getByText("pending admin", { exact: true }).first()).toBeVisible();

  await login(page, ADMIN, "admin");
  await page.goto("/admin/approvals");
  const changeCard = page.locator('[data-testid^="campaign-change-"]').filter({
    hasText: reductionReason,
  });
  await expect(changeCard).toBeVisible();
  await changeCard.getByLabel("Campaign change decision reason").fill(decisionReason);
  await changeCard.getByRole("button", { name: "Approve change" }).click();
  await expect(changeCard).not.toBeVisible();

  await login(page, ADVERTISER, "advertiser");
  await page.goto("/advertiser/campaigns");
  await page.getByRole("link", { name: "Demo Lagos Mobility Campaign" }).click();
  await expect(page.getByText(`Decision: ${decisionReason}`)).toBeVisible();
});
