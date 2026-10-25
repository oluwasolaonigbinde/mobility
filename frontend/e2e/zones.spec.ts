import { test, expect, type Page } from "@playwright/test";
import { randomUUID } from "node:crypto";
import type { components } from "../src/lib/api/schema";
import { cleanupIsolatedCampaign } from "./support/campaign-fixture";

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
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.waitForURL("**/advertiser");
}

test("campaign areas stay read-only when running and draft deletion requires confirmation", async ({
  page,
}) => {
  await loginAsAdvertiser(page);

  // Running campaigns expose coverage history; editing belongs to a draft.
  await page.goto("/advertiser/campaigns");
  await page
    .getByRole("table")
    .getByRole("link", { name: "Marula Kitchens — Abuja Lunch Routes" })
    .click();
  await page.waitForURL(/\/advertiser\/campaigns\/[0-9a-f-]{36}$/);
  const base = page.url();
  const sourceId = new URL(base).pathname.split("/").at(-1);
  await page.getByRole("link", { name: "View coverage history", exact: true }).click();
  await page.waitForURL(/\/map$/);
  await page.goto(`${base}/zones`);

  // Zone list from the backend
  await expect(page.getByText("Central Business District")).toBeVisible();
  await expect(page.getByText("Ahmadu Bello Way offices")).toBeVisible();
  await expect(page.getByText("Three Arms Zone")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Areas · 3", exact: true })).toBeVisible();

  // The running campaign's real map is visible, with no editing controls.
  await expect(page.getByTestId("zones-map").locator("canvas")).toBeVisible();
  await expect(page.getByRole("button", { name: "Draw area", exact: true })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Delete Central Business District" })).toHaveCount(
    0,
  );

  const session = (await page.context().cookies()).find(
    (cookie) => cookie.name === (process.env.SESSION_COOKIE_NAME ?? "mobility_session"),
  );
  if (!session) throw new Error("The area journey requires an advertiser session");
  const headers = { Authorization: `Bearer ${session.value}` };
  const apiBase = process.env.E2E_API_BASE_URL ?? "http://localhost:8000";
  const source = await page.request.get(
    `${apiBase}/api/v1/advertiser/campaigns/${sourceId}/zones`,
    { headers },
  );
  expect(source.status()).toBe(200);
  const sourceAreas = (await source.json()).items as components["schemas"]["CampaignZoneRead"][];
  expect(sourceAreas).toHaveLength(3);
  let draftId: string | undefined;
  try {
    const created = await page.request.post(`${apiBase}/api/v1/advertiser/campaigns`, {
      headers,
      data: {
        name: `E2E editable areas ${randomUUID()}`,
        status: "draft",
        budget_amount: "1000000.00",
        start_at: new Date(Date.now() + 86400000).toISOString(),
        end_at: new Date(Date.now() + 14 * 86400000).toISOString(),
      },
    });
    expect(created.status()).toBe(201);
    draftId = ((await created.json()) as { id: string }).id;
    expect(draftId).toMatch(/^[0-9a-f-]{36}$/);
    await page.goto(`/advertiser/campaigns/${draftId}`);
    await page.getByRole("link", { name: "Choose your area", exact: true }).click();
    await page.waitForURL(new RegExp(`/campaigns/${draftId}/zones$`));
    await expect(page.getByRole("button", { name: "Draw area", exact: true })).toBeVisible();
    for (const area of sourceAreas) {
      const added = await page.request.post(
        `${apiBase}/api/v1/advertiser/campaigns/${draftId}/zones`,
        {
          headers,
          data: { name: area.name, zone_type: area.zone_type, geometry: area.geometry },
        },
      );
      expect(added.status()).toBe(201);
      expect((await added.json()).campaign_id).toBe(draftId);
    }
    await page.reload();
    await expect(page.getByRole("heading", { name: "Areas · 3", exact: true })).toBeVisible();
    await expect(page.getByTestId("zones-map").locator("canvas")).toBeVisible();
    await expect(page.getByRole("button", { name: "Draw area", exact: true })).toBeVisible();
    await page.getByRole("button", { name: "Delete Central Business District" }).click();
    const confirmation = page.getByRole("alertdialog");
    await expect(confirmation).toContainText("Delete Central Business District?");
    await confirmation.getByRole("button", { name: "Keep area" }).click();
    await expect(confirmation).not.toBeVisible();
    const retained = await page.request.get(
      `${apiBase}/api/v1/advertiser/campaigns/${draftId}/zones`,
      { headers },
    );
    expect(retained.status()).toBe(200);
    const retainedAreas = (await retained.json())
      .items as components["schemas"]["CampaignZoneRead"][];
    expect(retainedAreas.map((area) => area.name).sort()).toEqual(
      sourceAreas.map((area) => area.name).sort(),
    );
  } finally {
    if (draftId) cleanupIsolatedCampaign(draftId);
  }
});
