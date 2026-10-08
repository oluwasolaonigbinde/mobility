import { randomUUID } from "node:crypto";
import { expect, test, type Page } from "@playwright/test";

async function login(page: Page, email: string, password: string, destination: string) {
  await page.goto("/login");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.waitForURL(`**/${destination}`);
}

async function adminCampaign(page: Page, name: string) {
  const session = (await page.context().cookies()).find(
    (cookie) => cookie.name === "mobility_session",
  );
  const response = await page.request.get(
    `${process.env.E2E_API_BASE_URL ?? "http://localhost:8000"}/api/v1/admin/campaigns?q=${encodeURIComponent(name)}`,
    { headers: { Authorization: `Bearer ${session!.value}` } },
  );
  expect(response.ok()).toBe(true);
  const campaign = (await response.json()).items.find(
    (item: { name: string }) => item.name === name,
  );
  expect(campaign).toBeTruthy();
  await page.goto(`/admin/campaigns/${campaign.id}#money`);
  return campaign;
}

test("admin can discover campaign commercial billing", async ({ page }) => {
  await login(page, "admin@demo.mobility.local", "DemoAdmin12345!", "admin");
  await page
    .getByRole("navigation", { name: "Primary" })
    .getByRole("link", { name: /^Money/ })
    .click();
  await expect(page.getByRole("heading", { name: "Money", exact: true })).toBeVisible();
  await page.getByRole("link", { name: "Invoices & payments", exact: true }).click();
  await page.getByRole("link", { name: "Marula Kitchens — Wuse Lunch Routes" }).click();
  await page.waitForURL(/\/campaigns\/[a-f0-9-]{36}/);
  await expect(page.getByRole("heading", { name: "Quotation" })).toBeVisible();
  await expect(page.getByText("Accepted", { exact: true }).first()).toBeVisible();
  await expect(page.getByText("Pay before production", { exact: true }).first()).toBeVisible();
});

test("admin company update persists and is visible to the advertiser", async ({ page }) => {
  const billingContact = `Billing E2E ${Date.now()}`;
  await login(page, "admin@demo.mobility.local", "DemoAdmin12345!", "admin");
  const campaign = await adminCampaign(page, "Marula Kitchens — Wuse Lunch Routes");
  await page.goto(`/admin/advertisers/${campaign.organization.id}#details`);
  await page.getByLabel("Billing contact").fill(billingContact);
  await page.getByRole("button", { name: "Save company profile" }).click();
  await expect(page).toHaveURL(/saved=1/, { timeout: 20_000 });
  await expect(page.getByRole("status")).toContainText("Company profile saved.");
  await page.reload();
  await expect(page.getByLabel("Billing contact")).toHaveValue(billingContact);

  await page.context().clearCookies();
  await login(page, "advertiser@demo.mobility.local", "DemoAdvertiser12345!", "advertiser");
  await page.goto("/advertiser/company");
  await expect(page.getByLabel("Billing contact")).toHaveValue(billingContact);
});

test("advertiser sees canonical company, billing and accepted terms", async ({ page }) => {
  await login(page, "advertiser@demo.mobility.local", "DemoAdvertiser12345!", "advertiser");
  await page.getByRole("link", { name: "Company", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Company profile" })).toBeVisible();
  await expect(page.getByLabel("Legal or trading name")).toHaveValue("Marula Kitchens");
  await page.getByRole("link", { name: "Billing", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Billing history" })).toBeVisible();
  await expect(page.getByText(/Issued NGN invoices can be paid through Paystack/i)).toBeVisible();
  await page.goto("/advertiser/campaigns");
  await page.getByRole("link", { name: "Marula Kitchens — Wuse Lunch Routes" }).click();
  await page.waitForURL(/\/campaigns\/[a-f0-9-]{36}/);
  await expect(page.getByRole("heading", { name: "Commercial terms" })).toBeVisible();
  await expect(page.locator("span").filter({ hasText: /^Accepted$/ })).toBeVisible();
  await expect(page.getByRole("button", { name: "Request custom quotation" })).not.toBeVisible();
  await expect(page.getByText("Driver pay to date", { exact: true })).toBeVisible();
});

test("quotation acceptance and invoice facts survive role changes and reloads", async ({
  page,
}, testInfo) => {
  test.setTimeout(120_000);
  const campaignName = `Commercial E2E ${testInfo.project.name} ${Date.now()}`;
  const quoteReference = `QUOTE-${randomUUID()}`;

  await login(page, "advertiser@demo.mobility.local", "DemoAdvertiser12345!", "advertiser");
  const session = (await page.context().cookies()).find(
    (cookie) => cookie.name === (process.env.SESSION_COOKIE_NAME ?? "mobility_session"),
  );
  expect(session, "advertiser login must set the session cookie").toBeTruthy();
  const apiBase = process.env.E2E_API_BASE_URL ?? "http://localhost:8000";
  const created = await page.request.post(`${apiBase}/api/v1/advertiser/campaigns`, {
    headers: { Authorization: `Bearer ${session!.value}` },
    data: { name: campaignName, status: "draft", budget_amount: "1000000.00" },
  });
  expect(created.ok(), "isolated billing campaign setup must succeed").toBe(true);
  const campaignId = ((await created.json()) as { id: string }).id;
  await page.goto(`/advertiser/campaigns/${campaignId}`);
  await expect(page.getByRole("heading", { name: campaignName })).toBeVisible();
  await page.getByLabel("Quotation notes").fill("Two vehicles for a commercial contract test");
  await page.getByRole("button", { name: "Request custom quotation" }).click();
  await expect(page.getByText(/Quotation requested\. Terrax Media will post it here/)).toBeVisible({
    timeout: 15_000,
  });

  await page.context().clearCookies();
  await login(page, "admin@demo.mobility.local", "DemoAdmin12345!", "admin");
  await adminCampaign(page, campaignName);
  await page.getByLabel("Quote reference").fill(quoteReference);
  await page.getByLabel("Services rendered").fill("Vehicle media placement");
  await expect(page.getByLabel("Quantity (number of advert campaigns)")).toHaveValue("1");
  await page.getByLabel("Unit price before VAT").fill("100000");
  await expect(page.getByLabel("VAT rate (decimal, 0.075 = 7.5 %)")).toHaveValue("0.075");
  // The isolated campaign has no dates, so the required campaign dates start blank.
  await page.getByLabel("Campaign start date").fill("2026-10-01");
  await page.getByLabel("Campaign end date").fill("2026-10-31");
  await page.getByLabel("Vehicle count").fill("2");
  await page.getByLabel("Payment terms and supporting notes").fill("Payment before production");
  await page.getByRole("button", { name: "Save quotation version" }).click();
  await expect(page.getByText(new RegExp(quoteReference))).toBeVisible();

  await page.context().clearCookies();
  await login(page, "advertiser@demo.mobility.local", "DemoAdvertiser12345!", "advertiser");
  await page.goto("/advertiser/campaigns");
  await page.getByRole("link", { name: campaignName }).click();
  const quotation = page.getByLabel("Latest quotation for review");
  await expect(quotation.getByText(`${quoteReference} · revision 1`)).toBeVisible();
  await expect(quotation.getByRole("cell", { name: "₦100,000.00" })).toBeVisible();
  await expect(
    quotation.getByText("Production cost").locator("..").getByText("₦0.00"),
  ).toBeVisible();
  await expect(
    quotation.getByText("Net", { exact: true }).locator("..").getByText("₦100,000.00"),
  ).toBeVisible();
  await expect(quotation.getByText("₦7,500.00")).toBeVisible();
  await expect(quotation.getByText("₦107,500.00")).toBeVisible();
  await page.getByRole("checkbox", { name: /I reviewed the scope/ }).check();
  await page.getByRole("button", { name: "Accept these exact terms" }).click();
  await expect(
    page.getByLabel("Campaign preparation").getByText("Accepted", { exact: true }),
  ).toBeVisible();
  await page.reload();
  await expect(page.getByLabel("Accepted quotation receipt")).toContainText(quoteReference);

  await page.context().clearCookies();
  await login(page, "admin@demo.mobility.local", "DemoAdmin12345!", "admin");
  await adminCampaign(page, campaignName);
  await page.getByRole("button", { name: "Create invoice draft" }).click();
  await expect(page.getByText("Draft — no number assigned")).toBeVisible();
  await expect(page.getByText("Current amount due")).toBeVisible();
  await expect(page.getByText("Payment status")).toBeVisible();

  await page.context().clearCookies();
  await login(page, "advertiser@demo.mobility.local", "DemoAdvertiser12345!", "advertiser");
  await page.goto("/advertiser/billing");
  const history = page.getByRole("link", { name: campaignName }).locator("xpath=../..");
  await expect(history.getByText("Invoice and settlement history")).toBeVisible();
  await expect(history.getByText("Draft — number assigned on issue")).toBeVisible();
  await history.getByRole("link", { name: "View invoice" }).click();
  await expect(page.getByRole("heading", { name: "Draft invoice" })).toBeVisible();
  await expect(page.getByText("1 October 2026 – 31 October 2026 (31 days)")).toBeVisible();
  await expect(
    page.getByText("Invoice total (VAT inclusive)").locator("..").getByText("₦107,500.00"),
  ).toBeVisible();
});
