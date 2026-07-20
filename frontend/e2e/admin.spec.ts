import { test, expect, type Page } from "@playwright/test";

/**
 * Admin console smoke against the seeded stack — every section renders
 * real backend data. Mutations (user/org creation, trip payout pipeline)
 * were verified manually end-to-end; these keep the read surfaces honest.
 */

async function loginAsAdmin(page: Page) {
  await page.goto("/login");
  await page.getByLabel("Email").fill("admin@demo.mobility.local");
  await page.getByLabel("Password").fill("DemoAdmin12345!");
  await page.getByRole("button", { name: "Enter the network" }).click();
  await page.waitForURL("**/admin");
}

test("admin overview shows network counts and full nav", async ({ page }) => {
  await loginAsAdmin(page);
  await expect(page.getByRole("heading", { name: "Fleet & Trust Operations" })).toBeVisible();
  const nav = page.getByRole("navigation", { name: "Primary" }).first();
  for (const item of ["Users", "Drivers", "Vehicles", "Assignments", "Fraud", "Payouts", "Audit"]) {
    await expect(nav.getByRole("link", { name: item })).toBeVisible();
  }
});

test("users section lists accounts with role filter and create entry", async ({ page }) => {
  await loginAsAdmin(page);
  await page.goto("/admin/users");
  // Scoped to the table — the sidebar also shows the signed-in admin's name
  const main = page.locator("#main");
  await expect(main.locator("tbody tr").first()).toBeVisible();
  await expect(page.getByRole("link", { name: "+ Create user" })).toBeVisible();
  await page
    .getByRole("group", { name: "Filter by role" })
    .getByRole("link", { name: "admin" })
    .click();
  await expect(main.getByText("Demo Admin")).toBeVisible();
  // Role filter narrows to drivers
  await page
    .getByRole("group", { name: "Filter by role" })
    .getByRole("link", { name: "driver" })
    .click();
  await expect(main.getByText("Demo Driver")).toBeVisible();
  await expect(main.getByText("Demo Admin")).not.toBeVisible();
});

test("drivers and vehicles sections show the seeded fleet", async ({ page }) => {
  await loginAsAdmin(page);
  await page.goto("/admin/drivers");
  await expect(page.getByText("Demo Driver")).toBeVisible();
  await page.goto("/admin/vehicles");
  await expect(page.getByText("DEMO-001")).toBeVisible();
});

test("assignments section lists the seeded pairing", async ({ page }) => {
  await loginAsAdmin(page);
  await page.goto("/admin/assignments");
  await expect(page.getByText("Demo Lagos Mobility Campaign").first()).toBeVisible();
  await expect(page.getByRole("link", { name: "+ Offer assignment" })).toBeVisible();
});

test("fraud console renders with status filters", async ({ page }) => {
  await loginAsAdmin(page);
  await page.goto("/admin/fraud");
  await expect(page.getByRole("heading", { name: "Fraud console" })).toBeVisible();
  await expect(
    page.getByRole("group", { name: "Filter by status" }).getByRole("link", { name: "open" }),
  ).toBeVisible();
});

test("payouts section lists calculations and the trip pipeline", async ({ page }) => {
  await loginAsAdmin(page);
  await page.goto("/admin/payouts");
  await expect(page.getByRole("heading", { name: "Payouts" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Run pipeline" })).toBeVisible();
  // Seeded + processed calculations exist with final payouts
  await expect(page.getByText(/₦[\d,]+/).first()).toBeVisible();
});

test("audit trail shows login activity and supports filtering", async ({ page }) => {
  await loginAsAdmin(page);
  await page.goto("/admin/audit");
  await expect(page.getByRole("heading", { name: "Audit trail" })).toBeVisible();
  await expect(page.getByText("auth.login.succeeded").first()).toBeVisible();
  await page.getByPlaceholder("Action, e.g. auth.login.succeeded").fill("auth.login.succeeded");
  await page.getByRole("button", { name: "Filter" }).click();
  await expect(page).toHaveURL(/action=auth.login.succeeded/);
  await expect(page.getByText("auth.login.succeeded").first()).toBeVisible();
});
