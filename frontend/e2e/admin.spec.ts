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
  for (const item of ["Users", "Drivers", "Vehicles", "Assignments", "Fraud", "Payouts", "Billing", "Audit"]) {
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
  await expect(
    page.getByRole("group", { name: "Filter by status" }).getByRole("link", { name: "confirmed" }),
  ).toBeVisible();
});

test("fraud review moves an isolated open flag through acknowledgement to dismissal", async ({
  page,
}, testInfo) => {
  await loginAsAdmin(page);
  await page.goto("/admin/fraud");

  // Fresh rich-seed stacks contain several flags. Each browser project owns a
  // different row so their state transitions cannot race with one another.
  const projectRow = testInfo.project.name === "mobile-chrome" ? 1 : 0;
  const acknowledge = page.getByRole("button", { name: "Acknowledge" }).nth(projectRow);
  test.skip(!(await acknowledge.isVisible().catch(() => false)), "No isolated seeded open flag");

  const card = acknowledge.locator(
    'xpath=ancestor::*[starts-with(@data-testid, "fraud-flag-")][1]',
  );
  const testId = await card.getAttribute("data-testid");
  expect(testId).toBeTruthy();

  await acknowledge.click();
  const reviewedCard = page.getByTestId(testId!);
  await expect(reviewedCard.getByText("acknowledged", { exact: true })).toBeVisible();
  await reviewedCard.getByLabel("Review note").fill("Reviewed in the isolated E2E workflow.");
  await reviewedCard.getByRole("button", { name: "Dismiss flag" }).click();
  await expect(reviewedCard.getByText("dismissed", { exact: true })).toBeVisible();
  await expect(reviewedCard.getByText(/review is final/i)).toBeVisible();
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

test("hourly payout rules are versioned: create rule once, then append revisions", async ({
  page,
}, testInfo) => {
  // Each project mutates its own inert seeded campaign so parallel projects
  // never race on the same rule row / revision chain.
  const campaignName =
    testInfo.project.name === "mobile-chrome"
      ? "F7 Festive Island Wrap"
      : "F7 Airport Launch Draft";
  await loginAsAdmin(page);
  await page.goto("/admin/payouts/rules");
  await page.getByRole("group", { name: "Campaign" }).getByText(campaignName).click();
  await page.waitForURL("**/admin/payouts/rules?campaign=**");

  // Seeded campaigns may have no rule or a legacy payout_v1 rule. Creating a
  // new hourly rule or migrating that legacy row writes the genesis revision
  // atomically. Re-runs land on the immutable revision panel (MNY-06A).
  const createRule = page.getByRole("button", { name: "Create rule" });
  const updateLegacyRule = page.getByRole("button", { name: "Update rule" });
  if (
    (await createRule.isVisible().catch(() => false)) ||
    (await updateLegacyRule.isVisible().catch(() => false))
  ) {
    const modelGroup = page.getByRole("group", { name: "Payout model" });
    await modelGroup.getByRole("button", { name: /Hourly \+ daily cap/ }).click();
    await page.getByLabel("Hourly rate").fill("1250");
    await page.getByLabel("Daily payable-hours cap").fill("8");
    if (await createRule.isVisible().catch(() => false)) await createRule.click();
    else await updateLegacyRule.click();
  }

  await expect(page.getByRole("button", { name: "Create revision" })).toBeVisible();
  await expect(page.getByRole("button", { name: /Update rule/ })).not.toBeVisible();
  await expect(page.getByText("Revision history")).toBeVisible();
  await expect(page.getByText(/^r1$/).first()).toBeVisible();

  // Append a future-dated revision and see it top the newest-first chain.
  const reason = `e2e rate change ${Date.now()}`;
  const newestRevision = await page
    .getByText(/^r\d+$/)
    .first()
    .textContent();
  const revisionNumber = Number(newestRevision?.slice(1) ?? "1");
  // Advance farther for every existing revision so immediate re-runs remain
  // strictly after the previously scheduled effective time.
  const dt = new Date(Date.now() + (revisionNumber + 1) * 10 * 60 * 1000);
  const pad = (n: number) => String(n).padStart(2, "0");
  const local = `${dt.getFullYear()}-${pad(dt.getMonth() + 1)}-${pad(dt.getDate())}T${pad(
    dt.getHours(),
  )}:${pad(dt.getMinutes())}`;
  await page.getByLabel("Base hourly rate").fill("1305");
  await page.getByLabel("Premium hourly rate (optional)").fill("1600");
  await page.getByLabel("Daily payable-hours cap").fill("8");
  await page.getByLabel("Effective from (future)").fill(local);
  await page.getByLabel("Reason (audited)").fill(reason);
  await page.getByRole("button", { name: "Create revision" }).click();
  await expect(page.getByText("✓ Revision created")).toBeVisible();

  await page.reload();
  const topRow = page.locator("tbody tr").first();
  await expect(topRow.getByText(reason)).toBeVisible();
  await expect(topRow.getByText(/1,305\.00/)).toBeVisible();
});

test("corrections screen offers projection, draft creation and the order queue", async ({
  page,
}) => {
  await loginAsAdmin(page);
  await page.goto("/admin/payouts");
  // The retired direct recompute is replaced by a pointer to correction orders.
  await page.getByRole("link", { name: "correction orders →" }).click();
  await page.waitForURL("**/admin/payouts/corrections");
  await expect(page.getByRole("heading", { name: "Correction orders" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Preview delta" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Create draft order" })).toBeVisible();
  await expect(page.getByRole("group", { name: "Filter by status" })).toBeVisible();
});
