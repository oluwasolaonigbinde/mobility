import { expect, test, type Page } from "@playwright/test";

const accounts = [
  {
    role: "admin",
    email: "admin@demo.mobility.local",
    password: "DemoAdmin12345!",
  },
  {
    role: "advertiser",
    email: "advertiser@demo.mobility.local",
    password: "DemoAdvertiser12345!",
  },
  {
    role: "driver",
    email: "driver@demo.mobility.local",
    password: "DemoDriver12345!",
  },
] as const;

async function login(page: Page, account: (typeof accounts)[number]) {
  await page.goto("/login");
  await page.getByLabel("Email").fill(account.email);
  await page.getByLabel("Password").fill(account.password);
  await page.getByRole("button", { name: "Enter the network" }).click();
  await page.waitForURL(`**/${account.role}`);
}

for (const account of accounts) {
  test(`${account.role} sees the shared sanitized notification centre`, async ({ page }) => {
    await login(page, account);
    const trigger = page.getByRole("button", { name: /notifications/i });
    await expect(trigger).toBeVisible();
    await expect(trigger).toContainText("1");
    await trigger.click();
    await expect(page.getByRole("region", { name: "Notifications" })).toContainText(
      "Trip payment on hold",
    );
    await expect(page.getByRole("region", { name: "Notifications" })).not.toContainText(
      "fraud_flag_id",
    );
  });
}

test("advertiser changes the shared email preference while in-app stays mandatory", async ({
  page,
}, testInfo) => {
  await login(page, accounts[1]);
  await page.getByRole("button", { name: /notifications/i }).click();
  await expect(page.getByText("In-app notifications are always on.")).toBeVisible();
  const emailToggle = page.getByLabel("Transactional email");
  const expected = testInfo.project.name === "mobile-chrome";
  if ((await emailToggle.isChecked()) !== expected) {
    await emailToggle.click();
  }
  await expect(emailToggle).toBeChecked({ checked: expected });
  await page.reload();
  await page.getByRole("button", { name: /notifications/i }).click();
  await expect(page.getByLabel("Transactional email")).toBeChecked({ checked: expected });
  await expect(page.getByText("In-app notifications are always on.")).toBeVisible();
});
