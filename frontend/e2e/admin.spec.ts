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
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.waitForURL("**/admin");
}

async function openCampaign(page: Page, name: string) {
  const session = (await page.context().cookies()).find(
    (cookie) => cookie.name === "mobility_session",
  );
  const response = await page.request.get(
    `${process.env.E2E_API_BASE_URL ?? "http://localhost:8000"}/api/v1/admin/campaigns?q=${encodeURIComponent(name)}`,
    { headers: { Authorization: `Bearer ${session!.value}` } },
  );
  expect(response.ok()).toBe(true);
  const campaign = (await response.json()).items.find(
    (item: { name: string }) => item.name === name,
  );
  expect(campaign).toBeTruthy();
  await page.goto(`/admin/campaigns/${campaign.id}`);
}

test("admin home shows the department work queue and full nav", async ({ page }) => {
  await loginAsAdmin(page);
  await expect(page.getByRole("heading", { name: "Work queue" })).toBeVisible();
  for (const section of ["Operations", "Compliance", "Finance", "Customer Service", "Admin"]) {
    await expect(page.getByRole("heading", { name: section, exact: true })).toBeVisible();
  }
  const nav = page.getByRole("navigation", { name: "Primary" }).first();
  for (const item of [
    "Work queue",
    "Drivers",
    "Campaigns",
    "Advertisers",
    "Trip checks",
    "Money",
    "Support",
    "Settings",
  ]) {
    await expect(nav.getByRole("link", { name: item })).toBeVisible();
  }
});

test("staff settings show active, invited and suspended logins with safe suspension", async ({
  page,
}) => {
  await loginAsAdmin(page);
  await page.goto("/admin/settings/staff");
  const main = page.locator("#main");
  await expect(main.getByText("Hauwa Sani", { exact: true })).toBeVisible();
  await expect(main.getByText("Temitope Ojo", { exact: true })).toBeVisible();
  await expect(main.getByText("Aisha Garba", { exact: true })).toBeVisible();
  await expect(main.getByRole("link", { name: "Add staff login" })).toBeVisible();
  await main
    .locator("li")
    .filter({ hasText: "Hauwa Sani" })
    .getByRole("button", { name: "Suspend", exact: true })
    .click();
  const confirmation = page.getByRole("alertdialog");
  await expect(confirmation).toContainText("Suspend Hauwa Sani?");
  await confirmation.getByRole("button", { name: "Keep account active" }).click();
  await expect(confirmation).not.toBeVisible();
});

test("driver and vehicle hubs show the seeded fleet with safe suspension", async ({ page }) => {
  await loginAsAdmin(page);
  await page.goto("/admin/drivers?tab=active&q=Emeka");
  await page.getByRole("link", { name: /Emeka Nwankwo/ }).click();
  await expect(page.getByRole("heading", { name: "Emeka Nwankwo" })).toBeVisible();
  await page.getByRole("button", { name: "Suspend", exact: true }).first().click();
  await expect(page.getByRole("alertdialog")).toContainText("Suspend Emeka Nwankwo?");
  await page.getByRole("alertdialog").getByRole("button", { name: "Keep driver active" }).click();
  await expect(page.getByText("ABJ-482-KD", { exact: true }).first()).toBeVisible();
  await page.locator("#cars").getByRole("button", { name: "Suspend", exact: true }).click();
  await expect(page.getByRole("alertdialog")).toContainText("Suspend ABJ-482-KD?");
  await page.getByRole("alertdialog").getByRole("button", { name: "Keep vehicle active" }).click();
});

test("assignments section lists the seeded pairing", async ({ page }) => {
  await loginAsAdmin(page);
  await openCampaign(page, "Marula Kitchens — Wuse Lunch Routes");
  await expect(page.getByText("Marula Kitchens — Wuse Lunch Routes").first()).toBeVisible();
  await expect(page.getByText("Offer a job · Find drivers")).toBeVisible();
  const row = page.locator('#drivers div[id^="job-"]').filter({ hasText: "Emeka Nwankwo" }).first();
  const trigger = row.getByRole("button", { name: "Cancel" });
  await trigger.click();
  const confirmation = page.getByRole("alertdialog");
  await expect(confirmation).toContainText("Cancel Emeka Nwankwo?");
  await expect(confirmation.getByRole("button", { name: "Keep assignment" })).toBeFocused();
  for (let index = 0; index < 4; index += 1) {
    await page.keyboard.press("Tab");
    await expect
      .poll(() => confirmation.evaluate((dialog) => dialog.contains(document.activeElement)))
      .toBe(true);
  }
  await page.keyboard.press("Escape");
  await expect(confirmation).not.toBeVisible();
  await expect(trigger).toBeFocused();
});

test("fraud page renders with status filters", async ({ page }) => {
  await loginAsAdmin(page);
  await page.goto("/admin/trip-checks");
  await expect(page.getByRole("heading", { name: "Trip checks", exact: true })).toBeVisible();
  await expect(
    page
      .getByRole("navigation", { name: "Status", exact: true })
      .getByRole("link", { name: "Needs attention" }),
  ).toBeVisible();
  await expect(
    page
      .getByRole("navigation", { name: "Status", exact: true })
      .getByRole("link", { name: "Problem confirmed" }),
  ).toBeVisible();
});

test("fraud review moves an isolated open flag through acknowledgement to dismissal", async ({
  page,
}, testInfo) => {
  await loginAsAdmin(page);
  await page.goto("/admin/trip-checks");

  // Fresh rich-seed stacks contain several flags. Each browser project owns a
  // different row so their state transitions cannot race with one another.
  const projectRow = testInfo.project.name === "mobile-chrome" ? 1 : 0;
  await page
    .locator("main li")
    .filter({ hasText: "Needs attention" })
    .locator('a[href*="flag="]')
    .nth(projectRow)
    .click();
  const drawer = page.getByRole("dialog");
  await drawer.getByRole("button", { name: "Start review" }).click();
  await expect(drawer.getByLabel("Review note")).toBeVisible();
  await drawer
    .getByLabel("Review note")
    .fill("The route matches the delivery stops and the photos are clear.");
  await drawer.getByRole("button", { name: "Clear", exact: true }).click();
  await expect(drawer.getByText(/review is final/i)).toBeVisible();
});

test("payouts section lists calculations and the trip pipeline", async ({ page }) => {
  await loginAsAdmin(page);
  await page.goto("/admin/money");
  await expect(page.getByRole("heading", { name: "Money", exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Available earnings" })).toBeVisible();
  // Seeded + processed calculations exist with final payouts
  await expect(page.getByText(/₦[\d,]+/).first()).toBeVisible();
});

test("audit trail shows login activity and supports filtering", async ({ page }) => {
  await loginAsAdmin(page);
  await page.goto("/admin/settings/activity");
  await expect(page.getByRole("heading", { name: "Activity log", exact: true })).toBeVisible();
  await expect(page.locator("main tbody tr").first()).toBeVisible();
  await page.getByPlaceholder("Action, e.g. auth.login.succeeded").fill("auth.login.succeeded");
  await page.getByRole("button", { name: "Filter" }).click();
  await expect(page).toHaveURL(/action=auth.login.succeeded/);
  await expect(page.getByText("Auth login succeeded").first()).toBeVisible();
});

test("daily-rate terms show the frozen version and publishing controls", async ({ page }) => {
  await loginAsAdmin(page);
  await openCampaign(page, "Marula Kitchens — Wuse Lunch Routes");
  await page.locator("#pay-terms summary").click();
  await expect(page.locator("#pay-terms").getByText("Version history")).toBeVisible();
  await expect(page.locator("#pay-terms").getByText("Version 1", { exact: true })).toBeVisible();
  await expect(
    page
      .locator("#pay-terms")
      .getByText(/10,000/)
      .first(),
  ).toBeVisible();
  await expect(page.getByLabel("Day rate (₦)")).toBeVisible();
  await expect(page.getByRole("button", { name: "Publish daily rate" })).toBeVisible();
});

test("corrections screen offers projection, draft creation and the order queue", async ({
  page,
}) => {
  await loginAsAdmin(page);
  await page.goto("/admin/money");
  // The retired direct recompute is replaced by a pointer to correction orders.
  await page.getByRole("link", { name: "Corrections", exact: true }).click();
  await page.waitForURL("**tab=corrections*");
  await expect(page.locator('main a[href*="correction="]').first()).toBeVisible();
  await page.getByText("Prepare a pay correction").click();
  await expect(page.getByRole("button", { name: "Create pay correction" })).toBeVisible();
  await expect(page.getByRole("navigation", { name: "Correction status" })).toBeVisible();
});
