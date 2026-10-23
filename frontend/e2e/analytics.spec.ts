import { test, expect, type Page } from "@playwright/test";

/** Report + heatmap smoke against the seeded stack. */

async function loginAsAdvertiser(page: Page) {
  await page.goto("/login");
  await page.getByLabel("Email").fill("advertiser@demo.mobility.local");
  await page.getByLabel("Password").fill("DemoAdvertiser12345!");
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.waitForURL("**/advertiser");
}

async function openSeededCampaign(page: Page) {
  await page.goto("/advertiser/campaigns");
  await page.getByRole("link", { name: "Marula Kitchens — Abuja Lunch Routes" }).click();
  await page.waitForURL(/\/advertiser\/campaigns\/[0-9a-f-]{36}$/);
}

test("report keeps issued CSV and PDF downloads for the golden campaign", async ({ page }) => {
  await loginAsAdvertiser(page);
  await openSeededCampaign(page);
  await page.goto(`${page.url()}/report`);
  await page.waitForURL(/\/report$/);

  // S9 / D118 replaces the measurement screen with immutable report files.
  await expect(page.getByRole("heading", { name: "Download a report" })).toBeVisible();
  await expect(page.getByText(/integrity check/i)).not.toBeVisible();
  await expect(page.getByRole("link", { name: "Download CSV" }).first()).toBeVisible();
  await expect(page.getByRole("link", { name: "Download PDF" }).first()).toBeVisible();
  await expect(page.getByText(/PDF includes charts and creative previews/)).toBeVisible();
});

test("coverage map ranks the golden campaign's populated target zone", async ({ page }) => {
  await loginAsAdvertiser(page);
  await openSeededCampaign(page);
  await page.getByRole("link", { name: /Coverage map/ }).click();
  await page.waitForURL(/\/map$/);

  await expect(page.getByText("#1 Central Business District", { exact: true })).toBeVisible();
  await expect(page.getByText(/integrity check/i)).not.toBeVisible();
  await expect(
    page.getByText("No zone ranking is available for this report yet."),
  ).not.toBeVisible();
});

test("advertiser can request a chosen period for one or all campaigns", async ({ page }) => {
  await loginAsAdvertiser(page);
  await page.goto("/advertiser/reports");
  const campaign = page.getByLabel("Campaign", { exact: true });
  const periodEnd = await page.getByLabel("To", { exact: true }).inputValue();
  const periodStart = new Intl.DateTimeFormat("en-CA", { timeZone: "Africa/Lagos" }).format(
    new Date(Date.now() - 7 * 86400000),
  );
  await page.getByLabel("From", { exact: true }).fill(periodStart);
  for (const all of [false, true]) {
    await campaign.selectOption(all ? "all" : { label: "Marula Kitchens — Wuse Lunch Rush" });
    const selected = await campaign.inputValue();
    const responsePromise = page.waitForResponse(
      (response) =>
        response.url().endsWith("/api/advertiser/reports") &&
        response.request().method() === "POST",
    );
    await page.getByRole("button", { name: "Create report" }).click();
    const response = await responsePromise;
    expect(response.status()).toBe(202);
    expect(response.request().postDataJSON()).toMatchObject({
      start_date: periodStart,
      end_date: periodEnd,
      campaign_id: all ? null : selected,
    });
    await expect(page.getByRole("status").filter({ hasText: "Report requested." })).toBeVisible();
  }
});
