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

  await expect(page.getByRole("heading", { name: "Exposure heatmap" })).toBeVisible();
  await expect(page.getByTestId("heatmap-map").locator("canvas")).toBeVisible();
  // The initial scan over the seeded Lagos zones returns 12 cells
  await expect(page.getByText(/12 cells · 500m grid/i)).toBeVisible({ timeout: 15_000 });

  // Metric switch triggers a rescan and keeps the cells
  await page.getByRole("radio", { name: "GPS pings" }).click();
  await expect(page.getByText(/12 cells/i)).toBeVisible({ timeout: 15_000 });
});
