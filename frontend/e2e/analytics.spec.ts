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

test("report fails closed when the seeded campaign has no frozen measurement run", async ({
  page,
}) => {
  await loginAsAdvertiser(page);
  await openSeededCampaign(page);
  await page.getByRole("link", { name: /Campaign Performance Analysis/ }).click();
  await page.waitForURL(/\/report$/);

  await expect(
    page.getByRole("heading", { name: "Frozen analysis failed its integrity check" }),
  ).toBeVisible();
  await expect(page.getByText("MEASUREMENT_RUN_INTEGRITY_FAILURE")).toBeVisible();
  await expect(page.getByText("Daily breakdown")).not.toBeVisible();
});

test("coverage map fails closed without frozen measurement authority", async ({ page }) => {
  await loginAsAdvertiser(page);
  await openSeededCampaign(page);
  await page.getByRole("link", { name: /Coverage map/ }).click();
  await page.waitForURL(/\/map$/);

  await expect(
    page.getByRole("heading", { name: "Frozen analysis failed its integrity check" }),
  ).toBeVisible();
  await expect(page.getByText("MEASUREMENT_RUN_INTEGRITY_FAILURE")).toBeVisible();
  await expect(page.getByTestId("heatmap-map")).not.toBeVisible();
});
