import { test, expect, type Page } from "@playwright/test";

/**
 * Zones editor smoke against the seeded stack. Polygon *drawing* is
 * exercised in unit tests (geometry) and was verified manually — synthetic
 * pointer sequences into WebGL are too flaky for CI. Here we prove the
 * page renders real zone data on a live map and is reachable from the
 * campaign detail page.
 */

async function loginAsAdvertiser(page: Page) {
  await page.goto("/login");
  await page.getByLabel("Email").fill("advertiser@demo.mobility.local");
  await page.getByLabel("Password").fill("DemoAdvertiser12345!");
  await page.getByRole("button", { name: "Enter the network" }).click();
  await page.waitForURL("**/advertiser");
}

test("zones page renders the seeded campaign's zones on a map", async ({ page }) => {
  await loginAsAdvertiser(page);

  // Reach zones via the campaign detail link (proves the wiring, not just the URL)
  await page.goto("/advertiser/campaigns");
  await page.getByRole("link", { name: "Demo Lagos Mobility Campaign" }).click();
  await page.waitForURL(/\/advertiser\/campaigns\/[0-9a-f-]{36}$/);
  await page.getByRole("link", { name: /Targeting zones/ }).click();
  await page.waitForURL(/\/zones$/);

  // Zone list from the backend
  await expect(page.getByText("Demo Lagos Target Zone")).toBeVisible();
  await expect(page.getByText("Demo Lagos Bonus Zone")).toBeVisible();
  await expect(page.getByText("Demo Lagos Exclusion Zone")).toBeVisible();
  await expect(page.getByText("Zones · 3")).toBeVisible();

  // Map mounted with a WebGL canvas and the draw affordance
  await expect(page.getByTestId("zones-map").locator("canvas")).toBeVisible();
  await expect(page.getByRole("button", { name: /Draw zone/ })).toBeVisible();
});
