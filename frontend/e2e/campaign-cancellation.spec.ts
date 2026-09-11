import { expect, test, type Page } from "@playwright/test";
import {
  cleanupIsolatedCampaign,
  createIsolatedActiveCampaign,
} from "./support/campaign-fixture";

const ADVERTISER = {
  email: "advertiser@demo.mobility.local",
  password: "DemoAdvertiser12345!",
};

async function login(page: Page) {
  await page.goto("/login");
  await page.getByLabel("Email").fill(ADVERTISER.email);
  await page.getByLabel("Password").fill(ADVERTISER.password);
  await page.getByRole("button", { name: "Enter the network" }).click();
  await page.waitForURL("**/advertiser");
}

test("advertiser confirms one permanent campaign cutoff", async ({ page }) => {
  test.setTimeout(60_000);
  const { campaignId, campaignName } = createIsolatedActiveCampaign("E2E cancellation");
  try {
    await login(page);
    await page.goto("/advertiser/campaigns");
    await page.getByRole("link", { name: campaignName }).click();

    const cancellationHeading = page.getByRole("heading", { name: "Cancel campaign" });
    const panel = cancellationHeading.locator("..");
    await expect(panel).toBeVisible();
    const cancel = panel.getByRole("button", { name: "Cancel campaign permanently" });
    await expect(cancel).toBeDisabled();
    await panel.getByLabel("Reason").fill("Synthetic isolated cancellation journey");
    await panel
      .getByRole("checkbox", {
        name: "I understand this records a permanent cancellation cutoff.",
      })
      .check();
    await cancel.click();

    await expect(page.getByText("Cancelled", { exact: true }).first()).toBeVisible();
    await expect(cancellationHeading).not.toBeVisible();
  } finally {
    cleanupIsolatedCampaign(campaignId);
  }
});
