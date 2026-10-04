import { test, expect, type Page } from "@playwright/test";

/**
 * Cardvert Driver PWA smoke against the seeded stack. These read-only checks
 * prove app chrome, seeded data on every tab, and the install manifest only.
 */

async function loginAsDriver(page: Page) {
  await page.goto("/login");
  await page.getByLabel("Email").fill("driver@demo.mobility.local");
  await page.getByLabel("Password").fill("DemoDriver12345!");
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.waitForURL("**/driver");
}

test("driver home shows earnings and the active campaign with app chrome", async ({ page }) => {
  await loginAsDriver(page);
  await expect(page.getByText("Cardvert. DRIVER")).toBeVisible();
  await expect(page.getByText("Available for payment", { exact: true })).toBeVisible();
  // Active-campaign card names the campaign; recent activity lists whichever
  // campaigns the enriched seed wrote most recently — so assert presence, not
  // an exact count tied to seed ordering.
  await expect(
    page.getByText("Marula Kitchens — Lagos Lunch Routes", { exact: true }).first(),
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

test("jobs tab shows an offer alongside active and completed campaigns", async ({ page }) => {
  await loginAsDriver(page);
  await page
    .getByRole("navigation", { name: "Driver app" })
    .getByRole("link", { name: "Jobs" })
    .click();
  await page.waitForURL("**/driver/assignments");
  await expect(page.getByText("Marula Kitchens — Lagos Lunch Routes").first()).toBeVisible();
  await expect(page.getByText("Linden Harbour Clothing — Lagos Commute").first()).toBeVisible();
  await expect(page.getByText("Beryl Lane Grocers — Market Routes").first()).toBeVisible();
  await expect(page.getByText("Marula Kitchens — Wuse Weekend Catering").first()).toBeVisible();
  await expect(page.getByText("Marula Kitchens — Island Lunch Deliveries").first()).toBeVisible();
  await expect(page.getByText("Marula Kitchens — Ikeja Office Lunch").first()).toBeVisible();
  await expect(page.getByText("ABJ-482-KD · car", { exact: true })).toHaveCount(6);
  const goldenJob = page
    .locator(".rounded-panel")
    .filter({ has: page.getByText("Marula Kitchens — Lagos Lunch Routes", { exact: true }) })
    .filter({ has: page.getByRole("button", { name: "Deactivate", exact: true }) });
  await goldenJob.getByRole("button", { name: "Deactivate", exact: true }).click();
  const confirmation = page.getByRole("alertdialog");
  await expect(confirmation).toContainText("Deactivate Marula Kitchens — Lagos Lunch Routes?");
  await confirmation.getByRole("button", { name: "Keep campaign active" }).click();
  await expect(confirmation).not.toBeVisible();
});

test("earnings tab shows totals and a trip-traceable ledger", async ({ page }) => {
  await loginAsDriver(page);
  await page
    .getByRole("navigation", { name: "Driver app" })
    .getByRole("link", { name: "Earnings" })
    .click();
  await page.waitForURL("**/driver/earnings");
  await expect(page.getByText("Available for payment", { exact: true })).toBeVisible();
  await expect(page.getByText("Under review", { exact: true })).toBeVisible();
  await expect(page.getByText("Paid", { exact: true }).first()).toBeVisible();
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
  await expect(
    page.getByRole("button", { name: /Start trip|End trip|Check trip status/ }),
  ).toBeVisible();
  await expect(page.getByText("Set up this phone")).toBeVisible();
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
  await expect(page.getByText("ABJ-482-KD", { exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Your campaign journey" })).toBeVisible();
});

test("PWA manifest is public and correctly scoped", async ({ request }) => {
  // No auth cookie on this request — exactly how browsers fetch manifests
  const res = await request.get("/driver/manifest.webmanifest");
  expect(res.status()).toBe(200);
  const manifest = await res.json();
  expect(manifest.name).toBe("Cardvert Driver");
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
  await expect(page.getByText(/Daily-rate pay/).first()).toBeVisible();
  await expect(page.getByText("Entries for this trip")).toBeVisible();
  await expect(page.getByText("Trip payout").first()).toBeVisible();
});
