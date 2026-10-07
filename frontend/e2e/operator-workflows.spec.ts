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
  await page
    .locator("main")
    .getByRole("textbox", { name: /Search/ })
    .fill(value);
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

  await page.goto("/admin/drivers?tab=active");
  await search(page, "Okafor");
  await expect(main.getByText("Chinedu Okafor")).toBeVisible();
  await expect(main.getByText("Ngozi Eze")).toHaveCount(0);
  await expectNoHorizontalOverflow(page);

  await page.goto("/admin/drivers?source=cars");
  await search(page, "ABJ-482-KD");
  await expect(main.getByText("ABJ-482-KD")).toBeVisible();
  await expect(main.getByText("MUS-763-RS")).toHaveCount(0);

  await page.goto("/admin/drivers?tab=active");
  await search(page, "Tunde");
  await expect(main.getByText("Tunde Adebayo").first()).toBeVisible();
  await expect(main.getByText("Chinedu Okafor")).toHaveCount(0);
  await main.getByRole("link", { name: /Tunde Adebayo/ }).click();
  await expect(
    main.locator("#jobs").getByRole("link", { name: "Aster Vale Foods — Wuse Deliveries" }),
  ).toBeVisible();
  await expectNoHorizontalOverflow(page);
});

test("activation readiness never invites a second activation of active work", async ({ page }) => {
  await loginAsAdmin(page);
  await page.goto("/admin/drivers?tab=active&q=Tunde");
  await page.getByRole("link", { name: /Tunde Adebayo/ }).click();
  await page
    .locator("#jobs")
    .getByRole("link", { name: "Aster Vale Foods — Wuse Deliveries" })
    .click();
  const drawer = page.getByRole("dialog");
  await expect(drawer.getByText(/already active/i)).toBeVisible();
  await expect(drawer.getByRole("button", { name: /activate/i })).toHaveCount(0);
  await expectNoHorizontalOverflow(page);
  await page.goto("/admin/campaigns?tab=getting-ready&q=Jabi");
  await page.getByRole("link", { name: "Sable Ridge Travel — Jabi Travel Enquiries" }).click();
  await page
    .locator("#drivers")
    .getByRole("link", { name: "Installation photos and job details" })
    .first()
    .click();
  await expect(page.getByRole("dialog").getByRole("button", { name: /activate/i })).toHaveCount(0);
});

test("evidence and contact queues show recorded work and useful empty searches", async ({
  page,
}) => {
  await loginAsAdmin(page);
  await page.goto("/admin/drivers");
  await expect(page.getByText("Nneka Umeh")).toBeVisible();
  await page.goto("/admin/trip-checks?tab=late");
  await expect(page.locator('main a[href*="late="]').first()).toBeVisible();
  await page.goto("/admin/support?tab=contact");
  await expect(page.locator('main a[href*="task="]').first()).toBeVisible();
  await page.goto("/admin/drivers?tab=active&q=NoSuchPerson");
  await expect(page.getByText("No matching drivers.")).toBeVisible();
  await expectNoHorizontalOverflow(page);
});

test("approved driver account setup stays provider-neutral through its visible terminal state", async ({
  page,
}) => {
  const applicant = prepareApprovedApplicant();
  await loginAsAdmin(page);

  await page.goto(`/admin/drivers/applicant/${applicant.applicationId}`);
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
  await expect(page).toHaveURL(new RegExp(`/admin/drivers/applicant/${applicant.applicationId}$`));
});

test("payout selection explains ineligible credits and closeout keeps paid facts separate", async ({
  page,
}) => {
  await loginAsAdmin(page);

  await page.goto("/admin/money");
  await expect(page.getByRole("heading", { name: "Available earnings" })).toBeVisible();
  await expect(page.getByText("Current successful assessment required").first()).toBeVisible();
  await expect(page.getByRole("checkbox", { name: /Select Emeka Nwankwo/ }).first()).toBeDisabled();
  await expectNoHorizontalOverflow(page);
  await page.goto("/admin/campaigns?tab=live&q=Lunch");
  await page.getByRole("link", { name: "Marula Kitchens — Wuse Lunch Routes" }).click();
  await page.getByRole("link", { name: "Review settlement and payout position" }).click();
  const closeout = page.getByRole("dialog");
  await expect(
    closeout.getByRole("heading", { name: "Settlement and payout position" }),
  ).toBeVisible();
  await expect(closeout.getByText("Pay records marked paid: ₦189.70")).toBeVisible();
  await expect(closeout.getByText("Confirmed provider transfers: ₦189.70")).toBeVisible();
  await expect(closeout.getByRole("button", { name: /complete|close campaign/i })).toHaveCount(0);
  await expectNoHorizontalOverflow(page);
});
