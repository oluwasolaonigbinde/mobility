import { test, expect, type Page } from "@playwright/test";
import { execFileSync } from "node:child_process";
import path from "node:path";

/**
 * Operator workflows against the seeded real stack. Most checks are read-only;
 * the account-setup fixture performs controlled writes only after its helper
 * proves the isolated E2E configuration. Nothing here activates work, reserves
 * money or records a production decision.
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

function prepareApprovedApplicant(): { applicationId: string; applicantName: string } {
  const output = execFileSync(
    "docker",
    [
      "compose",
      "exec",
      "-T",
      "api",
      "python",
      "frontend/e2e/support/prepare-account-setup-application.py",
    ],
    {
      cwd: path.resolve(process.cwd(), ".."),
      encoding: "utf8",
      env: process.env,
    },
  );
  const result = output
    .trim()
    .split("\n")
    .findLast((line) => line.startsWith("{"));
  if (!result) throw new Error(`Account-setup fixture did not return JSON: ${output}`);
  return JSON.parse(result) as { applicationId: string; applicantName: string };
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

test("approved driver account setup stays provider-neutral through its visible terminal state", async ({
  page,
}) => {
  const applicant = prepareApprovedApplicant();
  await loginAsAdmin(page);

  await page.goto(`/admin/driver-applications/${applicant.applicationId}`);
  await expect(page.getByRole("heading", { name: applicant.applicantName })).toBeVisible();
  await page.getByRole("button", { name: "Start account setup" }).click();

  const confirmation = page.getByRole("alertdialog", {
    name: `Start account setup for ${applicant.applicantName}?`,
  });
  await expect(confirmation).toContainText("replaces any earlier unused setup link");
  await confirmation.getByRole("button", { name: "Create one-use setup link" }).click();

  await expect(
    page.getByRole("status").filter({
      hasText:
        "A one-use setup link was created and queued for delivery to the applicant's stored email. Delivery is not confirmed.",
    }),
  ).toBeVisible();
  await expect(page.getByRole("button", { name: "Start account setup" })).toHaveCount(0);
  await expect(page).toHaveURL(
    new RegExp(`/admin/driver-applications/${applicant.applicationId}$`),
  );
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
  await expect(page.getByText(/Economic ledger totals count each credit once/)).toBeVisible();
  await expect(page.getByText("No campaign earnings on this page.")).toBeVisible();
  await expect(page.getByText("No settlement has been recorded on this page.")).toBeVisible();
  await expect(
    page.getByText("Live transfers require an approved disbursement provider"),
  ).toBeVisible();
  await expect(page.getByRole("button", { name: /complete|close campaign/i })).toHaveCount(0);
  await expectNoHorizontalOverflow(page);
});
