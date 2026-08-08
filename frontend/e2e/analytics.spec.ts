import { test, expect, type Page } from "@playwright/test";

/** Report + heatmap smoke against the seeded stack. */

async function loginAsAdvertiser(page: Page) {
  await page.goto("/login");
  await page.getByLabel("Email").fill("advertiser@demo.mobility.local");
  await page.getByLabel("Password").fill("DemoAdvertiser12345!");
  await page.getByRole("button", { name: "Enter the network" }).click();
  await page.waitForURL("**/advertiser");
}

async function openSeededCampaign(page: Page) {
  await page.goto("/advertiser/campaigns");
  await page.getByRole("link", { name: "Demo Lagos Mobility Campaign" }).click();
  await page.waitForURL(/\/advertiser\/campaigns\/[0-9a-f-]{36}$/);
}

test("attribution report renders charts and the daily table", async ({ page }) => {
  await loginAsAdvertiser(page);
  await openSeededCampaign(page);
  await page.getByRole("link", { name: /Report/ }).click();
  await page.waitForURL(/\/report$/);

  await expect(page.getByRole("heading", { name: "Attribution report" })).toBeVisible();
  await expect(page.getByRole("img", { name: "Daily estimated impressions" })).toBeVisible();
  await expect(page.getByRole("img", { name: "Daily media spend" })).toBeVisible();
  // Seeded daily metrics: two analyzed trips on two days
  await expect(page.getByRole("cell", { name: "10,064" })).toBeVisible();
  await expect(page.getByText("Daily breakdown")).toBeVisible();
});

test("exposure heatmap loads cells for the seeded campaign", async ({ page }) => {
  await loginAsAdvertiser(page);
  await openSeededCampaign(page);
  await page.getByRole("link", { name: /Exposure map/ }).click();
  await page.waitForURL(/\/map$/);

  await expect(page.getByRole("heading", { name: "Where your campaign was seen" })).toBeVisible();
  await expect(page.getByTestId("heatmap-guide")).toContainText(
    "Each square is a 500m × 500m area",
  );
  await expect(page.getByRole("button", { name: "Scan visible area" })).toBeVisible();
  const zoneKey = page.getByLabel("Zone colour key");
  await expect(zoneKey.getByText("Target area", { exact: true })).toBeVisible();
  await expect(zoneKey.getByText("Bonus area", { exact: true })).toBeVisible();
  await expect(zoneKey.getByText("Excluded area", { exact: true })).toBeVisible();
  await expect(page.getByTestId("heatmap-map").locator("canvas")).toBeVisible();
  // The initial scan returns a populated grid (exact count varies as trips
  // accumulate — this is a live dataset, assert shape not snapshot)
  await expect(page.getByText(/[1-9]\d* areas · 500m grid/i)).toBeVisible({ timeout: 15_000 });
  await expect(page.getByTestId("metric-summary")).toContainText("estimated impressions");

  // Metric switch triggers a rescan, explains the selected data, and keeps the cells.
  await page.getByRole("radio", { name: "GPS pings" }).click();
  await expect(page.getByTestId("heatmap-guide")).toContainText(
    "Where did campaign vehicles report their location?",
  );
  await expect(page.getByTestId("metric-summary")).toContainText(
    /All [1-9]\d* mapped areas have the same value: 1 GPS update/,
    { timeout: 15_000 },
  );
  await expect(page.getByText("Same value in every area:")).toBeVisible();
});
