import { test, expect, type Page } from "@playwright/test";

/**
 * Full advertiser journey against the real stack (Next.js BFF + FastAPI +
 * Postgres seeded with demo data): login → campaigns list → create-campaign
 * wizard → detail page → status transition.
 *
 * Prereq: backend running (`docker compose up -d` + migrations + demo seed).
 */

const ADVERTISER = {
  email: "advertiser@demo.mobility.local",
  password: "DemoAdvertiser12345!",
};

async function loginAsAdvertiser(page: Page) {
  await page.goto("/login");
  await page.getByLabel("Email").fill(ADVERTISER.email);
  await page.getByLabel("Password").fill(ADVERTISER.password);
  await page.getByRole("button", { name: "Enter the network" }).click();
  await page.waitForURL("**/advertiser");
}

test("advertiser can sign in and see the dashboard", async ({ page }) => {
  await loginAsAdvertiser(page);
  await expect(page.getByRole("heading", { name: /Demo Mobility Advertiser/ })).toBeVisible();
  await expect(page.getByText("EST. IMPRESSIONS", { exact: false })).toBeVisible();
});

test("signed-out users are redirected to login", async ({ page }) => {
  await page.goto("/advertiser/campaigns");
  await page.waitForURL("**/login?from=%2Fadvertiser%2Fcampaigns");
  await expect(page.getByRole("button", { name: "Enter the network" })).toBeVisible();
});

test("login rejects bad credentials without leaking detail", async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel("Email").fill(ADVERTISER.email);
  await page.getByLabel("Password").fill("definitely-wrong-password");
  await page.getByRole("button", { name: "Enter the network" }).click();
  // Filtered: Next.js's route announcer is also role="alert".
  await expect(
    page.getByRole("alert").filter({ hasText: /invalid email or password/i }),
  ).toBeVisible();
  expect(page.url()).toContain("/login");
});

test("full campaign lifecycle: create via wizard, launch, pause", async ({ page }) => {
  const name = `E2E Campaign ${Date.now()}`;
  await loginAsAdvertiser(page);

  // List → wizard
  await page.goto("/advertiser/campaigns");
  await page.getByRole("link", { name: "+ New campaign" }).click();
  await page.waitForURL("**/advertiser/campaigns/new");

  // Step 1 — basics (leave dates empty: draft campaigns don't need them)
  await page.getByLabel("Campaign name *").fill(name);
  await page.getByLabel(/Total budget/).fill("1500000");
  await page.getByRole("button", { name: "Continue →" }).click();

  // Step 2 — one creative
  await expect(page.getByText("✓ Basics")).toBeVisible();
  await page.getByRole("button", { name: "+ Add creative" }).click();
  await page.getByLabel("Creative name *").fill("E2E door panel");
  await page.getByLabel("Asset URL").fill("https://cdn.example.com/e2e-panel.png");
  await page.getByRole("button", { name: "Continue →" }).click();

  // Step 3 — review shows what we entered
  await expect(page.getByText(name)).toBeVisible();
  await expect(page.getByText("1 attached")).toBeVisible();
  // The click triggers a server action + redirect; the button swaps to
  // "Creating…" and detaches mid-handshake, which can trap Playwright's
  // retry loop until the test budget dies. Bound the click and let the
  // URL wait below be the authoritative assertion.
  await page
    .getByRole("button", { name: "Create campaign" })
    .click({ timeout: 5_000 })
    .catch(() => {});

  // Detail page for the new campaign
  await page.waitForURL(/\/advertiser\/campaigns\/[0-9a-f-]{36}$/);
  await expect(page.getByRole("heading", { name })).toBeVisible();
  await expect(page.getByText("Draft", { exact: true })).toBeVisible();
  await expect(page.getByText("E2E door panel")).toBeVisible();

  // Draft → live
  await page.getByRole("button", { name: "Launch now" }).click();
  await expect(page.getByText("Live", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Pause" })).toBeVisible();

  // Live → paused
  await page.getByRole("button", { name: "Pause" }).click();
  await expect(page.getByText("Paused", { exact: true })).toBeVisible();

  // The list reflects the new campaign
  await page.goto("/advertiser/campaigns?status=paused");
  await expect(page.getByRole("link", { name })).toBeVisible();
});

test("wizard blocks invalid input at the basics step", async ({ page }) => {
  await loginAsAdvertiser(page);
  await page.goto("/advertiser/campaigns/new");

  // Empty name
  await page.getByRole("button", { name: "Continue →" }).click();
  await expect(page.getByText("Campaign name is required")).toBeVisible();

  // End before start
  await page.getByLabel("Campaign name *").fill("Validation check");
  await page.getByLabel("Starts").fill("2026-09-30T20:00");
  await page.getByLabel("Ends").fill("2026-08-01T08:00");
  await page.getByRole("button", { name: "Continue →" }).click();
  await expect(page.getByText("End must be after start")).toBeVisible();
});
