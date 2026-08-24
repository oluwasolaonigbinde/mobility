import { expect, test, type Page } from "@playwright/test";

async function login(page: Page, email: string, password: string, destination: string) {
  await page.goto("/login");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: "Enter the network" }).click();
  await page.waitForURL(`**/${destination}`);
}

test("admin can discover campaign commercial billing", async ({ page }) => {
  await login(page, "admin@demo.mobility.local", "DemoAdmin12345!", "admin");
  await page.getByRole("link", { name: "Billing", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Commercial billing" })).toBeVisible();
  await expect(page.getByText("Demo Lagos Mobility Campaign")).toBeVisible();
  await page.getByRole("link", { name: "Open billing" }).first().click();
  await expect(page.getByRole("heading", { name: "Quotation" })).toBeVisible();
  await expect(page.getByText(/The advertiser has not requested a quotation/i)).toBeVisible();
  await expect(page.getByRole("link", { name: "Edit company details" })).toBeVisible();
});

test("admin company update persists and is visible to the advertiser", async ({ page }) => {
  const billingContact = `Billing E2E ${Date.now()}`;
  await login(page, "admin@demo.mobility.local", "DemoAdmin12345!", "admin");
  await page.goto("/admin/billing");
  await page.getByRole("link", { name: "Open billing" }).first().click();
  await page.getByRole("link", { name: "Edit company details" }).click();
  await page.getByLabel("Billing contact").fill(billingContact);
  await page.getByRole("button", { name: "Save company profile" }).click();
  await expect(page.getByText("Company profile saved.")).toBeVisible();
  await page.reload();
  await expect(page.getByLabel("Billing contact")).toHaveValue(billingContact);

  await page.context().clearCookies();
  await login(page, "advertiser@demo.mobility.local", "DemoAdvertiser12345!", "advertiser");
  await page.goto("/advertiser/company");
  await expect(page.getByLabel("Billing contact")).toHaveValue(billingContact);
});

test("advertiser sees canonical company, billing and gated launch entries", async ({ page }) => {
  await login(page, "advertiser@demo.mobility.local", "DemoAdvertiser12345!", "advertiser");
  await page.getByRole("link", { name: "Company", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Company profile" })).toBeVisible();
  await expect(page.getByLabel("Legal or trading name")).toHaveValue("Demo Advertiser");
  await page.getByRole("link", { name: "Billing", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Billing history" })).toBeVisible();
  await expect(page.getByText(/Online payment checkout is unavailable/i)).toBeVisible();
  await page.goto("/advertiser/campaigns");
  await page.getByRole("link", { name: "Demo Lagos Mobility Campaign" }).click();
  await expect(page.getByRole("heading", { name: "Commercial terms" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Request custom quotation" })).toBeVisible();
  await expect(page.getByText("Driver campaign cost", { exact: true })).toBeVisible();
});

test("quotation acceptance and invoice facts survive role changes and reloads", async ({
  page,
}, testInfo) => {
  const campaignName = `Commercial E2E ${testInfo.project.name} ${Date.now()}`;
  const quoteReference = `QUOTE-${Date.now()}`;

  await login(page, "advertiser@demo.mobility.local", "DemoAdvertiser12345!", "advertiser");
  await page.goto("/advertiser/campaigns/new");
  await page.getByLabel("Campaign name *").fill(campaignName);
  await page.getByRole("button", { name: "Continue →" }).click();
  await page.getByRole("button", { name: "Continue →" }).click();
  await page.getByRole("button", { name: "Create campaign" }).click();
  await expect(page.getByRole("heading", { name: campaignName })).toBeVisible();
  await page.getByLabel("Quotation notes").fill("Two vehicles for a commercial contract test");
  await page.getByRole("button", { name: "Request custom quotation" }).click();
  await expect(page.getByText("In review", { exact: true })).toBeVisible();

  await page.context().clearCookies();
  await login(page, "admin@demo.mobility.local", "DemoAdmin12345!", "admin");
  await page.goto("/admin/billing");
  const campaignRow = page.locator("li").filter({ hasText: campaignName });
  await campaignRow.getByRole("link", { name: "Open billing" }).click();
  await page.getByLabel("Quote reference").fill(quoteReference);
  await page.getByLabel("Line-item description").fill("Vehicle media placement");
  await page.getByLabel("Net amount").fill("100000");
  await page.getByLabel("Tax rate (decimal)").fill("0.075");
  await page.getByLabel("Vehicle count").fill("2");
  await page.getByLabel("Payment terms / evidence notes").fill("Payment before production");
  await page.getByRole("button", { name: "Record immutable revision" }).click();
  await expect(page.getByText(new RegExp(quoteReference))).toBeVisible();

  await page.context().clearCookies();
  await login(page, "advertiser@demo.mobility.local", "DemoAdvertiser12345!", "advertiser");
  await page.goto("/advertiser/campaigns");
  await page.getByRole("link", { name: campaignName }).click();
  await page.getByRole("button", { name: "Accept immutable terms" }).click();
  await expect(page.getByText("Accepted", { exact: true })).toBeVisible();
  await page.reload();
  await expect(page.getByText(new RegExp(quoteReference))).toBeVisible();

  await page.context().clearCookies();
  await login(page, "admin@demo.mobility.local", "DemoAdmin12345!", "admin");
  await page.goto("/admin/billing");
  await page
    .locator("li")
    .filter({ hasText: campaignName })
    .getByRole("link", { name: "Open billing" })
    .click();
  await page.getByRole("button", { name: "Create invoice draft" }).click();
  await expect(page.getByText("Draft — no number assigned")).toBeVisible();
  await expect(page.getByText("Effective obligation")).toBeVisible();
  await expect(page.getByText("Payment status")).toBeVisible();

  await page.context().clearCookies();
  await login(page, "advertiser@demo.mobility.local", "DemoAdvertiser12345!", "advertiser");
  await page.goto("/advertiser/billing");
  const history = page.getByRole("link", { name: campaignName }).locator("xpath=../..");
  await expect(history.getByText("Invoice and settlement history")).toBeVisible();
  await expect(history.getByText("Draft — number assigned on issue")).toBeVisible();
});
