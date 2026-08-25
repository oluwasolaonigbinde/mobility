import { execFileSync } from "node:child_process";
import { randomUUID } from "node:crypto";
import { resolve } from "node:path";

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
  WHERE o.billing_email = 'billing@demo.mobility.local'
    AND c.name = :'campaign_name'
    AND (
      NULLIF(:'campaign_id', '') IS NULL
      OR c.id = NULLIF(:'campaign_id', '')::uuid
    )
);
DELETE FROM campaigns c
USING advertiser_organizations o
WHERE c.organization_id = o.id
  AND o.billing_email = 'billing@demo.mobility.local'
  AND c.name = :'campaign_name'
  AND (
    NULLIF(:'campaign_id', '') IS NULL
    OR c.id = NULLIF(:'campaign_id', '')::uuid
  );
RESET session_replication_role;

SELECT 1 / CASE WHEN count(*) = 0 THEN 1 ELSE 0 END
FROM campaigns c
JOIN advertiser_organizations o ON o.id = c.organization_id
WHERE o.billing_email = 'billing@demo.mobility.local'
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
  await page.getByRole("button", { name: "Enter the network" }).click();
  await page.waitForURL("**/advertiser");
}

async function loginAsAdmin(page: Page) {
  await page.context().clearCookies();
  await page.goto("/login");
  await page.getByLabel("Email").fill(ADMIN.email);
  await page.getByLabel("Password").fill(ADMIN.password);
  await page.getByRole("button", { name: "Enter the network" }).click();
  await page.waitForURL("**/admin");
}

test("advertiser can sign in and see the dashboard", async ({ page }) => {
  await loginAsAdvertiser(page);
  await expect(page.getByRole("heading", { name: /Demo Advertiser/ })).toBeVisible();
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

test("campaign submission and admin approval preserve immutable review history", async ({ page }) => {
  test.setTimeout(60_000);
  const name = `E2E Campaign ${randomUUID()}`;
  let campaignId: string | undefined;
  try {
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
    campaignId = page.url().split("/").at(-1);
    if (!campaignId || !/^[0-9a-f-]{36}$/.test(campaignId)) {
      throw new Error("Created campaign URL did not contain a valid campaign ID.");
    }
    await expect(page.getByRole("heading", { name })).toBeVisible();
    await expect(page.getByText("Draft", { exact: true })).toBeVisible();
    await expect(page.getByText("E2E door panel")).toBeVisible();

    // A draft can only enter the review lifecycle through its dedicated action.
    await expect(page.getByRole("button", { name: "Submit for review" })).toBeVisible();
    await expect(page.getByRole("button", { name: /launch|schedule|activate/i })).not.toBeVisible();
    await expect(page.getByRole("button", { name: "Request custom quotation" })).toBeVisible();

    await page.getByRole("button", { name: "Submit for review" }).click();
    await expect(page.getByText("Under admin review")).toBeVisible();
    await expect(page.getByText("Submitted snapshot SHA-256:")).toBeVisible();

    await loginAsAdmin(page);
    await page.goto("/admin/approvals");
    const approval = page.getByTestId(`campaign-approval-${campaignId}`);
    await expect(approval.getByRole("heading", { name })).toBeVisible();
    await expect(approval.getByText("Snapshot SHA-256:")).toBeVisible();
    await approval.getByRole("button", { name: "Approve" }).click();
    await page.reload();
    await expect(page.getByTestId(`campaign-approval-${campaignId}`)).not.toBeVisible();

    await loginAsAdvertiser(page);
    await page.goto(`/advertiser/campaigns/${campaignId}`);
    await expect(page.getByText("Approved", { exact: true }).first()).toBeVisible();
    await expect(page.getByText("Draft → Pending review")).toBeVisible();
    await expect(page.getByText("Pending review → Approved")).toBeVisible();
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
