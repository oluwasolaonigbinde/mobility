import { test, expect, type Page } from "@playwright/test";
import type { components } from "../src/lib/api/schema";

/** Report + heatmap smoke against the seeded stack. */

async function loginAsAdvertiser(page: Page) {
  await page.goto("/login");
  await page.getByLabel("Email").fill("advertiser@demo.mobility.local");
  await page.getByLabel("Password").fill("DemoAdvertiser12345!");
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.waitForURL("**/advertiser");
}

async function openSeededCampaign(page: Page) {
  await page.goto("/advertiser/campaigns");
  await page
    .getByRole("table")
    .getByRole("link", { name: "Marula Kitchens — Abuja Lunch Routes" })
    .click();
  await page.waitForURL(/\/advertiser\/campaigns\/[0-9a-f-]{36}$/);
}

test("report keeps issued CSV and PDF downloads for the golden campaign", async ({ page }) => {
  await loginAsAdvertiser(page);
  await openSeededCampaign(page);
  await page.goto(`${page.url()}/report`);
  await page.waitForURL(/\/report$/);

  // S9 / D118 replaces the measurement screen with immutable report files.
  await expect(page.getByRole("heading", { name: "Download a report" })).toBeVisible();
  await expect(page.getByText(/integrity check/i)).not.toBeVisible();
  await expect(page.getByRole("link", { name: "Download CSV" }).first()).toBeVisible();
  await expect(page.getByRole("link", { name: "Download PDF" }).first()).toBeVisible();
  await expect(page.getByText(/The PDF has charts and pictures of your advert/)).toBeVisible();
});

test("coverage history shows the golden campaign's protected area results", async ({ page }) => {
  await loginAsAdvertiser(page);
  await openSeededCampaign(page);
  await page.getByRole("link", { name: "View coverage history" }).click();
  await page.waitForURL(/\/map$/);

  const campaignId = new URL(page.url()).pathname.split("/").at(-2);
  const session = (await page.context().cookies()).find(
    (cookie) => cookie.name === (process.env.SESSION_COOKIE_NAME ?? "mobility_session"),
  );
  expect(session, "the advertiser report requires its authenticated session").toBeTruthy();
  const response = await page.request.get(
    `${process.env.E2E_API_BASE_URL ?? "http://localhost:8000"}/api/v1/advertiser/campaigns/${campaignId}/report`,
    { headers: { Authorization: `Bearer ${session!.value}` } },
  );
  expect(response.status()).toBe(200);
  const report = (await response.json()) as components["schemas"]["CampaignPerformanceRead"];
  expect(report.campaign_id).toBe(campaignId);
  const area = report.areas.find((item) => item.name === "Central Business District");
  if (!area) throw new Error("The golden three-car area result is missing from its report");
  expect(area.trip_count).toBeGreaterThan(0);
  expect(area.modelled_potential_contacts).not.toBeNull();
  const row = page.getByRole("row").filter({
    has: page.getByRole("rowheader", { name: area.name, exact: true }),
  });
  await expect(page.getByRole("heading", { name: "Results by area", exact: true })).toBeVisible();
  await expect(row).toBeVisible();
  await expect(row.getByRole("cell").nth(0)).toHaveText(
    new Intl.NumberFormat("en-NG").format(Math.round(area.trip_count)),
  );
  await expect(row.getByRole("cell").nth(1)).toHaveText(
    new Intl.NumberFormat("en-NG").format(Math.round(Number(area.modelled_potential_contacts))),
  );
  await expect(page.getByText(/integrity check/i)).not.toBeVisible();
  await expect(
    page.getByText(
      "Area results aren’t available for this period. You can still see your campaign totals.",
    ),
  ).not.toBeVisible();
});

test("advertiser can request a chosen period for one or all campaigns", async ({ page }) => {
  await loginAsAdvertiser(page);
  await page.goto("/advertiser/reports");
  const campaign = page.getByLabel("Campaign", { exact: true });
  const periodEnd = await page.getByLabel("To", { exact: true }).inputValue();
  const periodStart = new Intl.DateTimeFormat("en-CA", { timeZone: "Africa/Lagos" }).format(
    new Date(Date.now() - 7 * 86400000),
  );
  await page.getByLabel("From", { exact: true }).fill(periodStart);
  await expect(page.getByLabel("From", { exact: true })).toHaveValue(periodStart);
  for (const all of [false, true]) {
    await campaign.selectOption(all ? "all" : { label: "Marula Kitchens — Wuse Lunch Rush" });
    // Keep the requested dates authoritative; diagnose any hydration/state reset here.
    await expect(page.getByLabel("From", { exact: true })).toHaveValue(periodStart);
    await expect(page.getByLabel("To", { exact: true })).toHaveValue(periodEnd);
    const selected = await campaign.inputValue();
    const responsePromise = page.waitForResponse(
      (response) =>
        response.url().endsWith("/api/advertiser/reports") &&
        response.request().method() === "POST",
    );
    await page.getByRole("button", { name: "Create report" }).click();
    const response = await responsePromise;
    expect(response.status()).toBe(202);
    expect(response.request().postDataJSON()).toMatchObject({
      start_date: periodStart,
      end_date: periodEnd,
      campaign_id: all ? null : selected,
    });
    await expect(page.getByRole("status").filter({ hasText: "Report requested." })).toBeVisible();
  }
});
