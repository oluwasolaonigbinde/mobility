import { test, expect, type Page } from "@playwright/test";

/**
 * Vantage Driver PWA smoke against the seeded stack. Read-only: trip
 * start/end with live GPS was verified manually (geolocation stubbing);
 * these prove the app chrome, real data on every tab, and installability.
 */

async function loginAsDriver(page: Page) {
  await page.goto("/login");
  await page.getByLabel("Email").fill("driver@demo.mobility.local");
  await page.getByLabel("Password").fill("DemoDriver12345!");
  await page.getByRole("button", { name: "Enter the network" }).click();
  await page.waitForURL("**/driver");
}

test("driver home shows earnings and the active campaign with app chrome", async ({ page }) => {
  await loginAsDriver(page);
  await expect(page.getByText("Vantage. DRIVER")).toBeVisible();
  await expect(page.getByText("Batch-payable earnings", { exact: true })).toBeVisible();
  // Active-campaign card names the campaign; recent activity lists whichever
  // campaigns the enriched seed wrote most recently — so assert presence, not
  // an exact count tied to seed ordering.
  await expect(
    page.getByText("Demo Lagos Mobility Campaign", { exact: true }).first(),
  ).toBeVisible();
  await expect(page.getByText("Recent activity")).toBeVisible();
  await expect(page.getByText("Every earning links back to a verified trip.")).toBeVisible();
  await expect(page.getByText("Campaigns", { exact: true })).toBeVisible();
  // Bottom tab bar — the app chrome
  const nav = page.getByRole("navigation", { name: "Driver app" });
  for (const tab of ["Home", "Jobs", "Track", "Earnings", "Profile"]) {
    await expect(nav.getByRole("link", { name: tab })).toBeVisible();
  }
});

test("jobs tab tells a three-campaign lifecycle story", async ({ page }) => {
  await loginAsDriver(page);
  await page
    .getByRole("navigation", { name: "Driver app" })
    .getByRole("link", { name: "Jobs" })
    .click();
  await page.waitForURL("**/driver/assignments");
  await expect(page.getByText("Demo Lagos Mobility Campaign")).toBeVisible();
  await expect(page.getByText("Airtel Lagos Commute")).toBeVisible();
  await expect(page.getByText("PalmPay Market Routes")).toBeVisible();
  await expect(page.getByText("DEMO-001 · car", { exact: true })).toHaveCount(3);
  // Seeded assignment is active → the one offered action is Deactivate
  await expect(page.getByRole("button", { name: "Deactivate" })).toBeVisible();
});

test("earnings tab shows totals and a trip-traceable ledger", async ({ page }) => {
  await loginAsDriver(page);
  await page
    .getByRole("navigation", { name: "Driver app" })
    .getByRole("link", { name: "Earnings" })
    .click();
  await page.waitForURL("**/driver/earnings");
  await expect(page.getByText("Pending", { exact: true })).toBeVisible();
  await expect(page.getByText("Lifetime earned", { exact: true })).toBeVisible();
  await expect(page.getByText("Payout journey")).toBeVisible();
  // Ledger rows are links into the per-trip earnings breakdown.
  await expect(page.locator('a[href*="/driver/earnings/trips/"]').first()).toBeVisible();
});

test("track tab offers trip control for the active assignment", async ({ page }) => {
  await loginAsDriver(page);
  await page
    .getByRole("navigation", { name: "Driver app" })
    .getByRole("link", { name: "Track" })
    .click();
  await page.waitForURL("**/driver/track");
  // Either ready-to-start or already tracking — both are valid live states
  await expect(page.getByRole("button", { name: /Start trip|End trip/ })).toBeVisible();
  await expect(page.getByText("How a trip becomes earnings")).toBeVisible();
  await expect(page.getByText("Recent verified activity")).toBeVisible();
});

test("profile tab shows driver details and vehicles", async ({ page }) => {
  await loginAsDriver(page);
  await page
    .getByRole("navigation", { name: "Driver app" })
    .getByRole("link", { name: "Profile" })
    .click();
  await page.waitForURL("**/driver/profile");
  await expect(page.getByText("driver@demo.mobility.local")).toBeVisible();
  await expect(page.getByRole("button", { name: "Save details" })).toBeVisible();
  await expect(page.getByText("DEMO-001")).toBeVisible();
  await expect(page.getByText("Driver readiness")).toBeVisible();
});

test("PWA manifest is public and correctly scoped", async ({ request }) => {
  // No auth cookie on this request — exactly how browsers fetch manifests
  const res = await request.get("/driver/manifest.webmanifest");
  expect(res.status()).toBe(200);
  const manifest = await res.json();
  expect(manifest.name).toBe("Vantage Driver");
  expect(manifest.scope).toBe("/driver");
  expect(manifest.display).toBe("standalone");
  expect(manifest.icons.length).toBeGreaterThanOrEqual(2);
});

test("ledger rows open the trip earnings breakdown", async ({ page }) => {
  await loginAsDriver(page);
  await page.goto("/driver/earnings");
  await page.locator('a[href*="/driver/earnings/trips/"]').first().click();
  await page.waitForURL("**/driver/earnings/trips/**");
  await expect(page.getByRole("heading", { name: "Trip earnings" })).toBeVisible();
  await expect(page.getByText("This trip earned")).toBeVisible();
  // Renders whichever model the trip was computed under (v1 fallback copy or
  // the v2 rate-x-time equation) - no model assumption (architecture 16.1).
  await expect(
    page.getByText(/Computed under the previous per-km formula|verified time/).first(),
  ).toBeVisible();
  await expect(page.getByText("Entries for this trip")).toBeVisible();
  await expect(page.getByText("Trip payout").first()).toBeVisible();
});
