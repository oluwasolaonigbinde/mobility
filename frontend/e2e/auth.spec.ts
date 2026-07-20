import { expect, test, type Page } from "@playwright/test";

const TEMPORARY_PASSWORD = "TemporaryPass123!";
const NEW_PASSWORD = "ChangedPassword123!";

async function login(page: Page, email: string, password: string) {
  await page.goto("/login");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: "Enter the network" }).click();
}

async function createUser(page: Page, role: "advertiser" | "driver", email: string) {
  await login(page, "admin@demo.mobility.local", "DemoAdmin12345!");
  await page.waitForURL("**/admin");
  await page.goto("/admin/users/new");
  await page.getByText(role === "driver" ? "Driver" : "Advertiser", { exact: true }).click();
  await page.getByLabel("Full name").fill(`F7 ${role}`);
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Temporary password").fill(TEMPORARY_PASSWORD);
  if (role === "advertiser") {
    await page.getByLabel("Organization name").fill(`F7 Org ${Date.now()}`);
  }
  await page.getByRole("button", { name: "Create account" }).click();
  await page.waitForURL("**/admin/users");
  await page.context().clearCookies();
  await page.goto("/login");
}

async function completePasswordChange(page: Page) {
  await page.getByLabel("Current password").fill(TEMPORARY_PASSWORD);
  await page.getByLabel("New password", { exact: true }).fill(NEW_PASSWORD);
  await page.getByLabel("Confirm new password").fill(NEW_PASSWORD);
  await page.getByRole("button", { name: "Update password" }).click();
}

test("admin-created advertiser must replace the temporary password", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "chromium", "desktop portal scenario");
  const email = `f7e2e-advertiser-${Date.now()}@demo.mobility.local`;
  await createUser(page, "advertiser", email);
  await login(page, email, TEMPORARY_PASSWORD);
  await page.waitForURL("**/change-password");
  const preChangeCookies = await page.context().cookies();
  await completePasswordChange(page);
  await page.waitForURL("**/advertiser");
  await expect(page.getByRole("button", { name: /Sign out/ })).toBeVisible({ timeout: 15_000 });

  // A password change revokes every older token. A stale cookie must still be
  // able to reach the login form instead of looping between /login and /.
  await page.context().clearCookies();
  await page.context().addCookies(preChangeCookies);
  await page.goto("/login");
  await expect(page.getByLabel("Email")).toBeVisible();
});

test("repeated login failures surface the 429 retry message", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "chromium", "one project only — the IP and global buckets are shared");
  test.setTimeout(180_000);
  // The per-account bucket is the primary limiter; local/CI runs export a
  // relaxed threshold (see docs/runbook.md), so read it instead of assuming 5.
  const maxFailures = Number(process.env.LOGIN_RATE_LIMIT_ACCOUNT_MAX_FAILURES ?? "5");
  const email = `f7e2e-limited-${Date.now()}@demo.mobility.local`;

  const limitMessage = page.getByText(/Too many attempts\. Try again in \d+ seconds\./);

  await page.goto("/login");
  for (let attempt = 0; attempt <= maxFailures + 2; attempt += 1) {
    await page.getByLabel("Email").fill(email);
    await page.getByLabel("Password").fill("WrongPassword123!");
    await page.getByRole("button", { name: "Enter the network" }).click();
    // The submit button re-enables only after the server action settles and
    // React has applied the returned form state, so the alert is current here.
    await expect(page.getByRole("button", { name: "Enter the network" })).toBeEnabled({
      timeout: 30_000,
    });
    if (await limitMessage.isVisible()) {
      break;
    }
  }
  await expect(limitMessage).toBeVisible();
});

test("admin-created driver changes password inside the driver PWA scope", async ({
  page,
}, testInfo) => {
  test.skip(testInfo.project.name !== "mobile-chrome", "mobile driver scenario");
  const email = `f7e2e-driver-${Date.now()}@demo.mobility.local`;
  await createUser(page, "driver", email);
  await login(page, email, TEMPORARY_PASSWORD);
  await page.waitForURL("**/driver/change-password");
  await completePasswordChange(page);
  await page.waitForURL("**/driver");
  await expect(page).toHaveURL(/\/driver$/);
});
