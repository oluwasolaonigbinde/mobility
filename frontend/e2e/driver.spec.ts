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
  await expect(
    page.locator("header").getByRole("link", { name: "Terrax Media Cardvert", exact: true }),
  ).toBeVisible();
  await expect(page.getByRole("heading", { name: "Your earnings", exact: true })).toBeVisible();
  await expect(page.getByText(/^Paid .*₦10,000/)).toBeVisible();
  // Active-campaign card names the campaign; recent activity lists whichever
  // campaigns the enriched seed wrote most recently — so assert presence, not
  // an exact count tied to seed ordering.
  await expect(
    page.getByText("Marula Kitchens — Abuja Lunch Routes", { exact: true }).first(),
  ).toBeVisible();
  await expect(page.getByRole("button", { name: "Start trip", exact: true })).toBeVisible();
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
  await expect(page.getByText("Marula Kitchens — Abuja Lunch Routes").first()).toBeVisible();
  await expect(page.getByText("Linden Harbour Clothing — Abuja Commute").first()).toBeVisible();
  await expect(page.getByText("Beryl Lane Grocers — Market Routes").first()).toBeVisible();
  await expect(page.getByText("Marula Kitchens — Wuse Weekend Catering").first()).toBeVisible();
  await expect(
    page.getByText("Marula Kitchens — Central Area Lunch Deliveries").first(),
  ).toBeVisible();
  await expect(page.getByText("Marula Kitchens — Utako Office Lunch").first()).toBeVisible();
  await expect(page.getByText(/Car ABJ-482-KD/)).toHaveCount(6);
  const goldenJob = page
    .locator(".rounded-panel")
    .filter({ has: page.getByText("Marula Kitchens — Abuja Lunch Routes", { exact: true }) })
    .filter({ has: page.locator("summary").filter({ hasText: "Job options" }) });
  await goldenJob.locator("summary").filter({ hasText: "Job options" }).click();
  await goldenJob.getByRole("button", { name: "Stop this job", exact: true }).click();
  const confirmation = page.getByRole("alertdialog");
  await expect(confirmation).toContainText("Stop Marula Kitchens — Abuja Lunch Routes?");
  await confirmation.getByRole("button", { name: "Keep this job" }).click();
  await expect(confirmation).not.toBeVisible();
});

test("earnings tab shows totals and a trip-traceable ledger", async ({ page }) => {
  await loginAsDriver(page);
  await page
    .getByRole("navigation", { name: "Driver app" })
    .getByRole("link", { name: "Earnings" })
    .click();
  await page.waitForURL("**/driver/earnings");
  await expect(page.getByRole("heading", { name: "Earnings", exact: true })).toBeVisible();
  await expect(page.getByText(/^Paid /).first()).toBeVisible();
  await page.locator("summary").first().click();
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
  await expect(page.getByRole("heading", { name: "Track", exact: true })).toBeVisible();
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
  await expect(page.getByRole("heading", { name: "Your history", exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Sign out", exact: true })).toBeVisible();
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
  await page.locator("summary").first().click();
  await page.locator('a[href*="/driver/earnings/trips/"]').first().click();
  await page.waitForURL("**/driver/earnings/trips/**");
  await expect(page.getByRole("heading", { name: "Trip earnings" })).toBeVisible();
  await expect(page.getByText("This trip earned")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Miles counted", exact: true })).toBeVisible();
  await expect(page.getByText("Entries for this trip")).toBeVisible();
  await expect(page.getByText("Trip payout").first()).toBeVisible();
});
