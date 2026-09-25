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
  await page.getByRole("link", { name: "Demo Lagos Mobility Campaign" }).click();
  await page.waitForURL(/\/advertiser\/campaigns\/[0-9a-f-]{36}$/);
}

test("report says no analysis exists yet when the seeded campaign has no frozen run", async ({
  page,
}) => {
  await loginAsAdvertiser(page);
  await openSeededCampaign(page);
  await page.getByRole("link", { name: /Campaign Performance Analysis/ }).click();
  await page.waitForURL(/\/report$/);

  await expect(page.getByRole("heading", { name: "No report is available yet" })).toBeVisible();
  await expect(page.getByText(/integrity check/i)).not.toBeVisible();
  await expect(page.getByText("Daily breakdown")).not.toBeVisible();
});

test("coverage map says no analysis exists yet without a frozen run", async ({ page }) => {
  await loginAsAdvertiser(page);
  await openSeededCampaign(page);
  await page.getByRole("link", { name: /Coverage map/ }).click();
  await page.waitForURL(/\/map$/);

  await expect(page.getByRole("heading", { name: "No report is available yet" })).toBeVisible();
  await expect(page.getByText(/integrity check/i)).not.toBeVisible();
  await expect(page.getByTestId("heatmap-map")).not.toBeVisible();
});
