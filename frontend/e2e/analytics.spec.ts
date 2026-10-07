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
  await page.getByRole("link", { name: "Marula Kitchens — Wuse Lunch Routes" }).click();
  await page.waitForURL(/\/advertiser\/campaigns\/[0-9a-f-]{36}$/);
}

test("report shows issued daily figures for the golden campaign", async ({ page }) => {
  await loginAsAdvertiser(page);
  await openSeededCampaign(page);
  await page.getByRole("link", { name: /Campaign Performance Analysis/ }).click();
  await page.waitForURL(/\/report$/);

  await expect(page.getByText(/^Based on all \d+ completed trips$/)).toBeVisible();
  await expect(page.getByText(/integrity check/i)).not.toBeVisible();
  await expect(page.getByText("Daily breakdown")).toBeVisible();
  await expect(page.getByRole("row")).toHaveCount(5);
});

test("coverage map ranks the golden campaign's populated target zone", async ({ page }) => {
  await loginAsAdvertiser(page);
  await openSeededCampaign(page);
  await page.getByRole("link", { name: /Coverage map/ }).click();
  await page.waitForURL(/\/map$/);

  await expect(page.getByText("#1 Wuse district", { exact: true })).toBeVisible();
  await expect(page.getByText(/integrity check/i)).not.toBeVisible();
  await expect(
    page.getByText("No zone ranking is available for this report yet."),
  ).not.toBeVisible();
});

test("another campaign shows its report being prepared", async ({ page }) => {
  await loginAsAdvertiser(page);
  await page.goto("/advertiser/campaigns");
  await page.getByRole("link", { name: "Marula Kitchens — Wuse Lunch Rush" }).click();
  await page.waitForURL(/\/advertiser\/campaigns\/[0-9a-f-]{36}$/);
  await page.goto(`${page.url()}/report`);
  await expect(
    page.getByRole("heading", { name: "Your campaign report is being prepared" }),
  ).toBeVisible();
});
