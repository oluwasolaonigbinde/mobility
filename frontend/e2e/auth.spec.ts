import { expect, test, type Page } from "@playwright/test";
import { spawnSync } from "node:child_process";
import path from "node:path";

const TEMPORARY_PASSWORD = "TemporaryPass123!";
const NEW_PASSWORD = "ChangedPassword123!";

async function login(page: Page, email: string, password: string) {
  await page.goto("/login");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: "Sign in" }).click();
}

async function createDriver(page: Page, email: string) {
  await login(page, "admin@demo.mobility.local", "DemoAdmin12345!");
  await page.waitForURL("**/admin");
  await page.goto("/admin/drivers/new");
  await expect(page.getByRole("region", { name: "Create driver login" })).toBeVisible();
  await expect(
    page.getByRole("region", { name: "Add profile for an existing login" }),
  ).toBeVisible();
  await expect(page.getByLabel("Driver user")).toBeVisible();
  await page.getByLabel("Full name").fill("F7 driver");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Temporary password").fill(TEMPORARY_PASSWORD);
  await page.getByRole("button", { name: "Create account" }).click();
  await page.waitForURL("**/admin/drivers");
  await page.context().clearCookies();
  await page.goto("/login");
}

async function completePasswordChange(page: Page) {
  await page.getByLabel("Current password").fill(TEMPORARY_PASSWORD);
  await page.getByLabel("New password", { exact: true }).fill(NEW_PASSWORD);
  await page.getByLabel("Confirm new password").fill(NEW_PASSWORD);
  await page.getByRole("button", { name: "Update password" }).click();
}

test("staff company invite requires one password setup before normal advertiser sign-in", async ({
  page,
}, testInfo) => {
  test.skip(testInfo.project.name !== "chromium", "desktop portal scenario");
  const email = `f7e2e-advertiser-${Date.now()}@example.com`;
  await login(page, "admin@demo.mobility.local", "DemoAdmin12345!");
  await page.waitForURL("**/admin");
  await page.goto("/admin/advertisers/new");
  await page.getByLabel("Company name").fill(`F7 Org ${Date.now()}`);
  await page.getByLabel("Login email").fill(email);
  await expect(page.getByLabel("Temporary password")).toHaveCount(0);
  await page.getByRole("button", { name: "Add company and send invite" }).click();
  await page.waitForURL(/\/admin\/advertisers\/[0-9a-f-]{36}#people$/);
  const fixture = spawnSync(
    "docker",
    [
      "compose",
      "exec",
      "-T",
      "api",
      "python",
      "frontend/e2e/support/read-advertiser-invite.py",
      email,
    ],
    { cwd: path.resolve(process.cwd(), ".."), encoding: "utf8", env: process.env },
  );
  if (fixture.status !== 0)
    throw new Error("The isolated advertiser invite fixture was unavailable.");
  let issued: { token?: string };
  try {
    issued = JSON.parse(
      fixture.stdout
        .trim()
        .split("\n")
        .findLast((line) => line.startsWith("{")) ?? "{}",
    );
  } catch {
    throw new Error("The isolated advertiser invite fixture returned no usable capability.");
  }
  expect(typeof issued.token).toBe("string");
  await page.context().clearCookies();
  await login(page, email, TEMPORARY_PASSWORD);
  await expect(
    page.getByRole("alert").filter({ hasText: /Invalid email or password/ }),
  ).toBeVisible();
  await page.evaluate((token: string) => {
    window.location.assign(`/advertiser-invite#${new URLSearchParams({ token })}`);
  }, issued.token!);
  await page.getByLabel("New password", { exact: true }).fill(NEW_PASSWORD);
  await page.getByLabel("Confirm new password").fill(NEW_PASSWORD);
  await page.getByRole("button", { name: "Set password" }).click();
  await expect(page.getByRole("status")).toContainText("Your login is ready.");
  expect(new URL(page.url()).hash.length).toBe(0);
  expect(
    (await page.context().cookies()).some(
      (cookie) => cookie.name === (process.env.SESSION_COOKIE_NAME ?? "mobility_session"),
    ),
  ).toBe(false);
  await login(page, email, NEW_PASSWORD);
  await page.waitForURL("**/advertiser");
  await expect(page.getByRole("heading", { level: 1 })).toContainText("F7 Org");
});

test("repeated login failures surface the 429 retry message", async ({ page }, testInfo) => {
  test.skip(
    testInfo.project.name !== "chromium",
    "one project only — the IP and global buckets are shared",
  );
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
    await page.getByRole("button", { name: "Sign in" }).click();
    // The submit button re-enables only after the server action settles and
    // React has applied the returned form state, so the alert is current here.
    await expect(page.getByRole("button", { name: "Sign in" })).toBeEnabled({
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
  await createDriver(page, email);
  await login(page, email, TEMPORARY_PASSWORD);
  await page.waitForURL("**/driver/change-password");
  const preChangeCookies = await page.context().cookies();
  await completePasswordChange(page);
  await page.waitForURL("**/driver");
  await expect(page).toHaveURL(/\/driver$/);
  // D62 driver password replacement still revokes every older session.
  await page.context().clearCookies();
  await page.context().addCookies(preChangeCookies);
  await page.goto("/login");
  await expect(page.getByLabel("Email")).toBeVisible();
});
