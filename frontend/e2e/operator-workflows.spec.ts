import { test, expect, type Page } from "@playwright/test";

/**
 * Read-only operator workflows against the seeded real stack: named discovery,
 * activation readiness, evidence queues and money closeout visibility. Nothing
 * here activates work, reserves money or records a decision.
 */

async function loginAsAdmin(page: Page) {
  await page.goto("/login");
  await page.getByLabel("Email").fill("admin@demo.mobility.local");
  await page.getByLabel("Password").fill("DemoAdmin12345!");
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.waitForURL("**/admin");
}

async function expectNoHorizontalOverflow(page: Page) {
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth - window.innerWidth,
  );
  expect(overflow).toBeLessThanOrEqual(1);
}

async function search(page: Page, value: string) {
  await page.getByLabel("Search this work list").fill(value);
  await page.getByRole("button", { name: "Search", exact: true }).click();
  await page.waitForURL(`**q=${encodeURIComponent(value)}*`);
}

test("named search narrows driver, vehicle and assignment work lists", async ({ page }) => {
  await loginAsAdmin(page);
  const main = page.locator("#main");

  await page.goto("/admin/drivers");
  await search(page, "Okafor");
  await expect(main.getByText("Chinedu Okafor")).toBeVisible();
  await expect(main.getByText("Ngozi Eze")).toHaveCount(0);
  await expectNoHorizontalOverflow(page);

  await page.goto("/admin/vehicles");
  await search(page, "DEMO-001");
  await expect(main.getByText("DEMO-001")).toBeVisible();
  await expect(main.getByText("DEMO-108")).toHaveCount(0);

  await page.goto("/admin/assignments");
  await search(page, "Tunde");
  await expect(main.getByText("Tunde Adebayo").first()).toBeVisible();
  await expect(main.getByText("Chinedu Okafor")).toHaveCount(0);
  await expectNoHorizontalOverflow(page);
});

test("activation readiness never invites a second activation of active work", async ({ page }) => {
  await loginAsAdmin(page);
  await page.goto("/admin/assignments?q=Tunde");
  await page.getByRole("link", { name: "Readiness and details" }).first().click();
  await expect(page.getByRole("heading", { name: "Activation readiness" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Already active" })).toBeVisible();
  await expect(page.getByRole("button", { name: /activate/i })).toHaveCount(0);
  await expect(
    page.getByText("This check does not confirm campaign closeout or cash settlement."),
  ).toBeVisible();
  await expectNoHorizontalOverflow(page);

  await page.goto("/admin/assignments?q=Airport");
  await page.getByRole("link", { name: "Readiness and details" }).first().click();
  await expect(page.getByRole("heading", { name: "Preparation required" })).toBeVisible();
  await expect(page.getByRole("button", { name: /activate/i })).toHaveCount(0);
});

test("evidence queues state empty results without implying completion", async ({ page }) => {
  await loginAsAdmin(page);

  await page.goto("/admin/driver-applications");
  await expect(page.getByText(/pending applications/i)).toBeVisible();
  await page.getByLabel("Include history").check();
  await page.getByRole("button", { name: "Search", exact: true }).click();
  await page.waitForURL("**history=true*");
  await expect(page.getByText(/recorded applications/i)).toBeVisible();

  await page.goto("/admin/late-data");
  await expect(page.getByText(/never reprices earnings or edits an issued report/)).toBeVisible();

  await page.goto("/admin/measurement");
  await expect(page.getByText("Missing or gated data is not a zero result.")).toBeVisible();

  await page.goto("/admin/contact");
  await expect(page.getByText(/No automated message is sent here/)).toBeVisible();
  await expectNoHorizontalOverflow(page);
});

test("payout selection explains ineligible credits and closeout keeps paid facts separate", async ({
  page,
}) => {
  await loginAsAdmin(page);

  await page.goto("/admin/payouts/batches");
  await expect(page.getByRole("heading", { name: "Payout batches" })).toBeVisible();
  await expect(page.getByText("Current successful assessment required").first()).toBeVisible();
  await expect(page.getByRole("checkbox", { name: /Select Demo Driver/ }).first()).toBeDisabled();
  await expectNoHorizontalOverflow(page);

  await page.goto("/admin/billing");
  await page.getByRole("link", { name: "Open billing" }).first().click();
  await page.getByRole("link", { name: "Review settlement and payout position" }).click();
  await expect(page.getByRole("heading", { name: "Settlement and payout position" })).toBeVisible();
  await expect(page.getByText(/Economic ledger paid:/).first()).toBeVisible();
  await expect(page.getByText(/Verified provider transfers:/).first()).toBeVisible();
  await expect(
    page.getByText("Live transfers require an approved disbursement provider"),
  ).toBeVisible();
  await expect(page.getByRole("button", { name: /complete|close campaign/i })).toHaveCount(0);
  await expectNoHorizontalOverflow(page);
});
