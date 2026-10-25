import { execFileSync } from "node:child_process";
import { randomUUID } from "node:crypto";
import { resolve } from "node:path";

import { test, expect, type Page } from "@playwright/test";
import type { components } from "../src/lib/api/schema";

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

const ADMIN = {
  email: "admin@demo.mobility.local",
  password: "DemoAdmin12345!",
};

const COMPOSE_FILE = resolve(__dirname, "../../docker-compose.yml");

function cleanupE2ECampaign(campaignId: string | undefined, campaignName: string) {
  const databaseContainer = process.env.E2E_DATABASE_CONTAINER;
  const databaseName = process.env.E2E_DATABASE_NAME ?? "mobility";
  const sql = `
SET session_replication_role = replica;
DELETE FROM campaign_review_events
WHERE campaign_id IN (
  SELECT c.id
  FROM campaigns c
  JOIN advertiser_organizations o ON o.id = c.organization_id
  WHERE o.billing_email = 'accounts@marulakitchens.ng'
    AND c.name = :'campaign_name'
    AND (
      NULLIF(:'campaign_id', '') IS NULL
      OR c.id = NULLIF(:'campaign_id', '')::uuid
    )
);
DELETE FROM campaigns c
USING advertiser_organizations o
WHERE c.organization_id = o.id
  AND o.billing_email = 'accounts@marulakitchens.ng'
  AND c.name = :'campaign_name'
  AND (
    NULLIF(:'campaign_id', '') IS NULL
    OR c.id = NULLIF(:'campaign_id', '')::uuid
  );
RESET session_replication_role;

SELECT 1 / CASE WHEN count(*) = 0 THEN 1 ELSE 0 END
FROM campaigns c
JOIN advertiser_organizations o ON o.id = c.organization_id
WHERE o.billing_email = 'accounts@marulakitchens.ng'
  AND c.name = :'campaign_name';
`;
  execFileSync(
    "docker",
    databaseContainer
      ? [
          "exec",
          "-i",
          databaseContainer,
          "psql",
          "-v",
          "ON_ERROR_STOP=1",
          "-v",
          `campaign_id=${campaignId ?? ""}`,
          "-v",
          `campaign_name=${campaignName}`,
          "-U",
          "mobility",
          "-d",
          databaseName,
        ]
      : [
          "compose",
          "-f",
          COMPOSE_FILE,
          "exec",
          "-T",
          "db",
          "psql",
          "-v",
          "ON_ERROR_STOP=1",
          "-v",
          `campaign_id=${campaignId ?? ""}`,
          "-v",
          `campaign_name=${campaignName}`,
          "-U",
          "mobility",
          "-d",
          databaseName,
        ],
    { input: sql, stdio: ["pipe", "pipe", "pipe"] },
  );
}

async function loginAsAdvertiser(page: Page) {
  await page.context().clearCookies();
  await page.goto("/login");
  await page.getByLabel("Email").fill(ADVERTISER.email);
  await page.getByLabel("Password").fill(ADVERTISER.password);
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.waitForURL("**/advertiser");
}

async function loginAsAdmin(page: Page) {
  await page.context().clearCookies();
  await page.goto("/login");
  await page.getByLabel("Email").fill(ADMIN.email);
  await page.getByLabel("Password").fill(ADMIN.password);
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.waitForURL("**/admin");
}

async function openCampaignSection(page: Page, id: "details" | "manage") {
  if ((await page.locator(`#${id}`).getAttribute("open")) === null) {
    await page.locator(`#${id} > summary`).click();
  }
}

test("advertiser can sign in without exposing suppressed dashboard results", async ({ page }) => {
  await loginAsAdvertiser(page);
  await expect(page.getByRole("heading", { name: /Marula Kitchens/, level: 1 })).toBeVisible({
    timeout: 20_000,
  });
  const session = (await page.context().cookies()).find(
    (cookie) => cookie.name === (process.env.SESSION_COOKIE_NAME ?? "mobility_session"),
  );
  expect(session, "advertiser login must set the session cookie").toBeTruthy();
  const apiBase = process.env.E2E_API_BASE_URL ?? "http://localhost:8000";
  const summary = await page.request.get(`${apiBase}/api/v1/advertiser/dashboard/summary`, {
    headers: { Authorization: `Bearer ${session!.value}` },
  });
  expect(summary.status()).toBe(409);
  expect((await summary.json()).error.code).toBe("DISCLOSURE_SUPPRESSED");
  await expect(
    page.getByText("Not enough cars yet to show estimated views.").first(),
  ).toBeVisible();
  await expect(page.getByRole("heading", { name: "On the road now", exact: true })).toBeVisible();
  await expect(page.getByText("Estimated ad exposure", { exact: true })).toHaveCount(0);
});

test("signed-out users are redirected to login", async ({ page }) => {
  await page.goto("/advertiser/campaigns");
  await page.waitForURL("**/login?from=%2Fadvertiser%2Fcampaigns");
  await expect(page.getByRole("button", { name: "Sign in" })).toBeVisible();
});

test("login rejects bad credentials without leaking detail", async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel("Email").fill(ADVERTISER.email);
  await page.getByLabel("Password").fill("definitely-wrong-password");
  await page.getByRole("button", { name: "Sign in" }).click();
  // Filtered: Next.js's route announcer is also role="alert".
  await expect(
    page.getByRole("alert").filter({ hasText: /invalid email or password/i }),
  ).toBeVisible();
  expect(page.url()).toContain("/login");
});

test("campaign submission and admin approval preserve immutable review history", async ({
  page,
}) => {
  test.setTimeout(60_000);
  const name = `E2E Campaign ${randomUUID()}`;
  let campaignId: string | undefined;
  try {
    await loginAsAdvertiser(page);

    // List → wizard
    await page.goto("/advertiser/campaigns");
    await page.getByRole("link", { name: "+ New campaign" }).click();
    await page.waitForURL("**/advertiser/campaigns/new");

    // Step 1 — basics. D38(d): review needs dates, a total budget and a target area.
    await page.getByLabel("Campaign name *").fill(name);
    await page.getByLabel("Starts, Nigeria time (WAT)").fill("2027-01-10T09:00");
    await page.getByLabel("Ends, Nigeria time (WAT)").fill("2027-02-10T18:00");
    await page.getByLabel(/Total budget/).fill("1500000");
    await page.getByRole("button", { name: "Continue →" }).click();

    // Saving Basics creates one recoverable draft before Areas (REQ-209).
    await expect(page).toHaveURL(/\/new\?campaignId=[0-9a-f-]{36}$/);
    const savedDraftId = new URL(page.url()).searchParams.get("campaignId");
    campaignId = savedDraftId ?? undefined;
    await expect(page.locator('[aria-current="step"]')).toHaveText("2 Areas");
    // Area drawing has its own journey; the API target-area setup below remains explicit.
    await page.getByRole("button", { name: "Continue →" }).click();
    await expect(page.getByRole("button", { name: "+ Add advert design" })).toBeVisible();
    await page.getByRole("button", { name: "Continue →" }).click();

    // Step 4 — review shows the saved draft without creating another campaign.
    await expect(page.getByText(name)).toBeVisible();
    await expect(page.getByRole("heading", { name: "Review your draft" })).toBeVisible();
    await expect(page.getByText("Add later", { exact: true })).toBeVisible();
    // Finish the saved draft; retain the bounded click and require its redirect.
    await page.getByRole("button", { name: "Finish draft" }).click({ timeout: 5_000 });

    // Detail page for the new campaign
    await page.waitForURL(/\/advertiser\/campaigns\/[0-9a-f-]{36}$/);
    campaignId = page.url().split("/").at(-1);
    expect(campaignId).toBe(savedDraftId);
    if (!campaignId || !/^[0-9a-f-]{36}$/.test(campaignId)) {
      throw new Error("Created campaign URL did not contain a valid campaign ID.");
    }
    await expect(page.getByRole("heading", { name })).toBeVisible();
    // The status chip beside the heading; the preparation summary repeats the status.
    await expect(
      page.getByRole("heading", { name }).locator("..").getByText("Draft", { exact: true }),
    ).toBeVisible();
    await expect(page.getByRole("link", { name: "Upload artwork", exact: true })).toBeVisible();

    // A draft can only enter the review lifecycle through its dedicated action.
    await openCampaignSection(page, "manage");
    await expect(page.getByRole("button", { name: "Submit for review" })).toBeVisible();
    await expect(page.getByRole("button", { name: /launch|schedule|activate/i })).not.toBeVisible();
    await openCampaignSection(page, "details");
    await expect(page.getByRole("button", { name: "Request custom quotation" })).toBeVisible();

    // Zone drawing is covered by the zones editor tests; add the target area through the API.
    const session = (await page.context().cookies()).find(
      (cookie) => cookie.name === (process.env.SESSION_COOKIE_NAME ?? "mobility_session"),
    );
    expect(session, "advertiser login must set the session cookie").toBeTruthy();
    const apiBase = process.env.E2E_API_BASE_URL ?? "http://localhost:8000";
    const zone = await page.request.post(
      `${apiBase}/api/v1/advertiser/campaigns/${campaignId}/zones`,
      {
        headers: { Authorization: `Bearer ${session!.value}` },
        data: {
          name: "E2E target area",
          zone_type: "target",
          geometry: {
            type: "Polygon",
            coordinates: [
              [
                [3.3, 6.4],
                [3.5, 6.4],
                [3.5, 6.6],
                [3.3, 6.6],
                [3.3, 6.4],
              ],
            ],
          },
        },
      },
    );
    expect(zone.ok(), "target area setup must succeed").toBe(true);
    await page.reload();

    await openCampaignSection(page, "manage");
    await page.getByRole("button", { name: "Submit for review" }).click();
    await expect(
      page.getByRole("region", { name: "Next step" }).getByText("Pending review", { exact: true }),
    ).toBeVisible();
    // D38(c): the submission fingerprint is no longer shown to advertisers.
    await expect(page.getByText(/Submission reference/)).not.toBeVisible();
    const readHistory = async () => {
      const currentSession = (await page.context().cookies()).find(
        (cookie) => cookie.name === (process.env.SESSION_COOKIE_NAME ?? "mobility_session"),
      );
      expect(
        Boolean(currentSession),
        "the history read requires the current advertiser session",
      ).toBe(true);
      const response = await page.request.get(
        `${apiBase}/api/v1/advertiser/campaigns/${campaignId}/review-history`,
        { headers: { Authorization: `Bearer ${currentSession!.value}` } },
      );
      expect(response.ok(), "the advertiser must read its own immutable review history").toBe(true);
      return (
        (await response.json()) as {
          items: components["schemas"]["CampaignReviewEventRead"][];
        }
      ).items;
    };
    const submittedHistory = await readHistory();
    const submission = submittedHistory.find((event) => event.new_status === "pending_review");
    expect(submission).toMatchObject({ prior_status: "draft", new_status: "pending_review" });
    expect(submission?.reviewed_snapshot_sha256).toMatch(/^[0-9a-f]{64}$/);

    await loginAsAdmin(page);
    await page.goto(`/admin/campaigns/${campaignId}`);
    await expect(page.getByRole("heading", { name })).toBeVisible();
    await page.getByRole("button", { name: "Approve", exact: true }).click();
    await expect(page.getByRole("button", { name: "Approve", exact: true })).not.toBeVisible();
    await page.reload();
    await expect(page.getByRole("button", { name: "Approve", exact: true })).not.toBeVisible();

    await loginAsAdvertiser(page);
    await page.goto(`/advertiser/campaigns/${campaignId}`);
    await expect(
      page.getByRole("region", { name: "Next step" }).getByText("Approved", { exact: true }),
    ).toBeVisible();
    await openCampaignSection(page, "details");
    const updates = page.getByRole("heading", { name: "Campaign updates" }).locator("..");
    await expect(updates.getByText(/^Pending review ·/)).toBeVisible();
    await expect(updates.getByText(/^Approved ·/)).toBeVisible();
    const approvedHistory = await readHistory();
    // Approval appends its decision and retains the exact prior submitted evidence.
    expect(approvedHistory.find((event) => event.id === submission!.id)).toEqual(submission);
    expect(approvedHistory.find((event) => event.new_status === "approved")).toMatchObject({
      prior_status: "pending_review",
      new_status: "approved",
      submission_event_id: submission!.id,
    });
    await expect(page.getByRole("button", { name: /launch|schedule|activate/i })).not.toBeVisible();
  } finally {
    cleanupE2ECampaign(campaignId, name);
  }
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
