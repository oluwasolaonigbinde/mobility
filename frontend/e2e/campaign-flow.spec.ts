import { execFileSync, spawnSync } from "node:child_process";
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

// Only booleans reach assertion diagnostics: an invalid aggregate may contain
// private values, including in unexpected keys or in place of scalar fields.
function requireAggregate(condition: boolean, field: string) {
  expect(condition, `Invalid aggregate projection: ${field}`).toBe(true);
}

function aggregateFields(value: unknown, keys: readonly string[], field: string) {
  requireAggregate(typeof value === "object" && value !== null && !Array.isArray(value), field);
  const record = value as Record<string, unknown>;
  const actualKeys = Object.keys(record);
  requireAggregate(
    actualKeys.length === keys.length && keys.every((key) => Object.hasOwn(record, key)),
    field,
  );
  return record;
}

const aggregateUuid = (value: unknown): value is string =>
  typeof value === "string" && /^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i.test(value);
const aggregateCurrency = (value: unknown) => typeof value === "string" && /^[A-Z]{3}$/.test(value);
const aggregateCount = (value: unknown) =>
  typeof value === "number" && Number.isSafeInteger(value) && value >= 0;
const aggregateDecimal = (value: unknown) =>
  typeof value === "string" &&
  /^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$/.test(value) &&
  Number.isFinite(Number(value));
const aggregatePeriod = (value: unknown) =>
  value === null ||
  (typeof value === "string" &&
    /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$/.test(value) &&
    Number.isFinite(Date.parse(value)));

function hasNoProhibitedAggregateFields(value: unknown): boolean {
  if (Array.isArray(value)) return value.every(hasNoProhibitedAggregateFields);
  if (typeof value !== "object" || value === null) return true;
  return Object.entries(value).every(([key, child]) => {
    const normalized = key.replace(/([a-z0-9])([A-Z])/g, "$1_$2").toLowerCase();
    // Approved organization/campaign/area IDs and report periods are validated
    // separately. This guard applies to aggregate responses, never live maps.
    const prohibited =
      /^(?:(?:driver|vehicle|user|profile|person|trip|assignment)_?ids?|drivers|vehicles|users|profiles|trips_by_driver|email|email_address|phone|phone_number|first_name|last_name|full_name|address|bank_account|account_number|password|token|access_token|refresh_token|authorization|cookie|cookies|gps|raw_gps|latitude|longitude|lat|lng|lon|coordinates|geometry|location|locations|position|positions|points|raw_points|fixes|samples|route|routes|trail|created_at|recorded_at|started_at|ended_at|timestamp|timestamps)$/;
    return !prohibited.test(normalized) && hasNoProhibitedAggregateFields(child);
  });
}

function validateDashboardAggregate(
  value: unknown,
): components["schemas"]["AdvertiserDashboardSummary"] {
  requireAggregate(hasNoProhibitedAggregateFields(value), "summary prohibited fields");
  const summary = aggregateFields(
    value,
    [
      "organization_id",
      "currency",
      "start_at",
      "end_at",
      "campaigns",
      "assignments",
      "trips",
      "impressions",
      "costs",
      "quality",
    ],
    "summary fields",
  );
  requireAggregate(aggregateUuid(summary.organization_id), "summary organization ID");
  requireAggregate(aggregateCurrency(summary.currency), "summary currency");
  requireAggregate(
    aggregatePeriod(summary.start_at) && aggregatePeriod(summary.end_at),
    "summary periods",
  );
  for (const [field, keys] of [
    [
      "campaigns",
      [
        "total",
        "draft",
        "pending_review",
        "approved",
        "rejected",
        "active",
        "paused",
        "finished",
        "cancelled",
      ],
    ],
    ["assignments", ["total", "offered", "accepted", "active", "cancelled", "finished"]],
    ["trips", ["total", "ended", "active"]],
  ] as const) {
    const counts = aggregateFields(summary[field], keys, `summary ${field}`);
    requireAggregate(Object.values(counts).every(aggregateCount), `summary ${field} counts`);
  }
  const impressions = aggregateFields(
    summary.impressions,
    [
      "estimated_impressions",
      "estimated_trip_count",
      "insufficient_data_trip_count",
      "excluded_trip_count",
      "average_confidence_score",
    ],
    "summary impressions",
  );
  for (const field of ["estimated_impressions", "average_confidence_score"]) {
    requireAggregate(aggregateDecimal(impressions[field]), `summary ${field}`);
  }
  for (const field of [
    "estimated_trip_count",
    "insufficient_data_trip_count",
    "excluded_trip_count",
  ]) {
    requireAggregate(aggregateCount(impressions[field]), `summary ${field}`);
  }
  const quality = aggregateFields(
    summary.quality,
    ["average_quality_score", "fraud_flags"],
    "summary quality",
  );
  requireAggregate(
    aggregateDecimal(quality.average_quality_score),
    "summary average quality score",
  );
  const flags = aggregateFields(
    quality.fraud_flags,
    ["open", "confirmed", "dismissed", "low", "medium", "high"],
    "summary fraud flags",
  );
  requireAggregate(Object.values(flags).every(aggregateCount), "summary fraud counts");
  const costs = aggregateFields(summary.costs, ["totals_by_currency"], "summary costs");
  requireAggregate(Array.isArray(costs.totals_by_currency), "summary cost array");
  for (const value of costs.totals_by_currency as unknown[]) {
    const cost = aggregateFields(
      value,
      ["currency", "final_payout_total", "gross_payout_total", "ledger_entry_count"],
      "summary cost fields",
    );
    requireAggregate(aggregateCurrency(cost.currency), "summary cost currency");
    requireAggregate(
      aggregateDecimal(cost.final_payout_total) && aggregateDecimal(cost.gross_payout_total),
      "summary payout totals",
    );
    requireAggregate(aggregateCount(cost.ledger_entry_count), "summary ledger count");
  }
  return value as components["schemas"]["AdvertiserDashboardSummary"];
}

function validateCampaignAggregate(
  value: unknown,
): components["schemas"]["CampaignPerformanceRead"] {
  requireAggregate(hasNoProhibitedAggregateFields(value), "campaign report prohibited fields");
  const report = aggregateFields(
    value,
    ["campaign_id", "start_at", "end_at", "totals", "areas", "completeness", "uncertainty"],
    "campaign report fields",
  );
  requireAggregate(aggregateUuid(report.campaign_id), "campaign report ID");
  requireAggregate(
    aggregatePeriod(report.start_at) && aggregatePeriod(report.end_at),
    "campaign report periods",
  );
  requireAggregate(
    typeof report.completeness === "string" && typeof report.uncertainty === "string",
    "campaign report metadata",
  );
  const totals = aggregateFields(
    report.totals,
    ["distance_m", "trip_count", "driving_days", "estimated_views"],
    "campaign totals",
  );
  for (const field of ["distance_m", "estimated_views"]) {
    requireAggregate(
      totals[field] === null || aggregateDecimal(totals[field]),
      `campaign ${field}`,
    );
  }
  for (const field of ["trip_count", "driving_days"]) {
    requireAggregate(totals[field] === null || aggregateCount(totals[field]), `campaign ${field}`);
  }
  requireAggregate(Array.isArray(report.areas), "campaign area array");
  for (const value of report.areas as unknown[]) {
    const area = aggregateFields(
      value,
      ["area_id", "name", "trip_count", "modelled_potential_contacts"],
      "campaign area fields",
    );
    requireAggregate(aggregateUuid(area.area_id), "campaign area ID");
    requireAggregate(typeof area.name === "string", "campaign area name");
    requireAggregate(aggregateCount(area.trip_count), "campaign area trip count");
    requireAggregate(
      area.modelled_potential_contacts === null ||
        aggregateDecimal(area.modelled_potential_contacts),
      "campaign area contacts",
    );
  }
  return value as components["schemas"]["CampaignPerformanceRead"];
}

test("advertiser sees only governed tenant aggregates and its campaign performance", async ({
  page,
}) => {
  await loginAsAdvertiser(page);
  await expect(page.getByRole("heading", { name: /Marula Kitchens/, level: 1 })).toBeVisible({
    timeout: 20_000,
  });
  const session = (await page.context().cookies()).find(
    (cookie) => cookie.name === (process.env.SESSION_COOKIE_NAME ?? "mobility_session"),
  );
  expect(session, "advertiser login must set the session cookie").toBeTruthy();
  const apiBase = process.env.E2E_API_BASE_URL ?? "http://localhost:8000";
  const headers = { Authorization: `Bearer ${session!.value}` };
  const meResponse = await page.request.get(`${apiBase}/api/v1/me`, { headers });
  expect(meResponse.status()).toBe(200);
  const me = (await meResponse.json()) as components["schemas"]["MeResponse"];
  const organization = me.advertiser_organization;
  if (!organization) throw new Error("The advertiser has no authenticated company");
  requireAggregate(aggregateUuid(organization.id), "authenticated organization ID");
  const fixture = spawnSync(
    "docker",
    [
      "compose",
      "exec",
      "-T",
      "api",
      "python",
      "frontend/e2e/support/read-advertiser-cohort.py",
      organization.id,
    ],
    { cwd: resolve(process.cwd(), ".."), encoding: "utf8", env: process.env },
  );
  if (fixture.status !== 0) throw new Error("The isolated numeric cohort proof was unavailable");
  let cohort: { trips: number; cars: number };
  try {
    cohort = JSON.parse(
      fixture.stdout
        .trim()
        .split("\n")
        .findLast((line) => line.startsWith("{")) ?? "{}",
    );
  } catch {
    throw new Error("The isolated numeric cohort proof was invalid");
  }
  expect(Number.isSafeInteger(cohort.cars)).toBe(true);
  expect(cohort.cars).toBeGreaterThanOrEqual(3);
  expect(Number.isSafeInteger(cohort.trips)).toBe(true);
  const summary = await page.request.get(`${apiBase}/api/v1/advertiser/dashboard/summary`, {
    headers,
  });
  expect(summary.status()).toBe(200);
  const aggregate = validateDashboardAggregate(await summary.json());
  requireAggregate(
    aggregate.organization_id === organization.id,
    "authenticated summary organization",
  );
  requireAggregate(aggregate.currency === organization.currency, "authenticated summary currency");
  requireAggregate(
    aggregate.start_at === null && aggregate.end_at === null,
    "unbounded summary periods",
  );
  requireAggregate(aggregate.trips.total === cohort.trips, "exact authenticated cohort trip count");
  const name = "Marula Kitchens — Abuja Lunch Routes";
  const card = page.locator(".portal-card").filter({
    has: page.getByRole("heading", { name, exact: true }),
  });
  await expect(card).toHaveCount(1);
  const link = await card.getByRole("link", { name, exact: true }).getAttribute("href");
  const campaignId = link?.split("/").at(-1);
  if (!aggregateUuid(campaignId))
    throw new Error("The named Home campaign has no valid campaign link");
  const reportResponse = await page.request.get(
    `${apiBase}/api/v1/advertiser/campaigns/${campaignId}/report`,
    { headers },
  );
  expect(reportResponse.status()).toBe(200);
  const report = validateCampaignAggregate(await reportResponse.json());
  requireAggregate(report.campaign_id === campaignId, "named Home campaign binding");
  const performance = card.getByRole("region", { name: "Campaign performance", exact: true });
  const views = performance
    .getByText("Estimated views", { exact: true })
    .locator("..")
    .locator("dd");
  const withheld = performance.getByText("Not enough cars yet to show estimated views.", {
    exact: true,
  });
  if (report.totals.estimated_views === null) {
    await expect(views).toHaveText("—");
    await expect(withheld).toBeVisible();
  } else {
    await expect(views).toHaveText(
      new Intl.NumberFormat("en-NG").format(Math.round(Number(report.totals.estimated_views))),
    );
    await expect(withheld).toHaveCount(0);
  }
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
    await expect(page.getByText(name, { exact: true })).toBeVisible();
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
