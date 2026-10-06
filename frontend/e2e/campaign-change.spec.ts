import { expect, test, type Page } from "@playwright/test";
import type { components } from "../src/lib/api/schema";
import { adminStatus } from "../src/lib/status/admin";
import { cleanupIsolatedCampaign, createIsolatedActiveCampaign } from "./support/campaign-fixture";

const ADVERTISER = {
  email: "advertiser@demo.mobility.local",
  password: "DemoAdvertiser12345!",
};
const ADMIN = {
  email: "admin@demo.mobility.local",
  password: "DemoAdmin12345!",
};

async function login(page: Page, credentials: typeof ADVERTISER, destination: string) {
  await page.context().clearCookies();
  await page.goto("/login");
  await page.getByLabel("Email").fill(credentials.email);
  await page.getByLabel("Password").fill(credentials.password);
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.waitForURL(`**/${destination}`);
}

test("advertiser preview and reasoned admin decision complete a mid-flight change", async ({
  page,
}) => {
  test.setTimeout(60_000);
  const { campaignId, campaignName } = createIsolatedActiveCampaign("E2E campaign change");
  const reductionReason = `Synthetic governed reduction for ${campaignName}`;
  const decisionReason = `Approved synthetic reduction for ${campaignName}`;
  const readRequests = async () => {
    const cookieName = process.env.SESSION_COOKIE_NAME ?? "mobility_session";
    const session = (await page.context().cookies()).find((cookie) => cookie.name === cookieName);
    expect(session, "the advertiser browser must establish its own session").toBeTruthy();
    const apiBase = process.env.E2E_API_BASE_URL ?? "http://localhost:8000";
    const response = await page.request.get(
      `${apiBase}/api/v1/advertiser/campaigns/${campaignId}/change-requests`,
      { headers: { Authorization: `Bearer ${session!.value}` } },
    );
    expect(response.ok(), "the advertiser must read its own campaign change requests").toBe(true);
    return (await response.json()).items as components["schemas"]["CampaignChangeRead"][];
  };

  try {
    await login(page, ADVERTISER, "advertiser");
    await page.goto("/advertiser/campaigns");
    await page.getByRole("link", { name: campaignName }).click();
    await expect(page.getByRole("heading", { name: "Campaign changes" })).toBeVisible();

    await page.getByLabel("Total budget").fill("999999999.00");
    await page
      .getByPlaceholder("Explain why this change is needed")
      .fill("Synthetic funded-scope expansion");
    await page.getByRole("button", { name: "Preview change" }).click();
    const expansionPreview = page.getByLabel("Change preview");
    await expect(expansionPreview.getByText("Can apply now")).toBeVisible();
    await expect(expansionPreview.getByText("NGN 0.00").first()).toBeVisible();
    await expansionPreview.getByRole("button", { name: "Confirm this change" }).click();
    await expect(page.getByText("✓ Campaign change confirmed.")).toBeVisible();
    await expect(page.getByText("Applied", { exact: true }).first()).toBeVisible();

    await page.getByLabel("Total budget").fill("999999998.00");
    await page.getByPlaceholder("Explain why this change is needed").fill(reductionReason);
    await page.getByRole("button", { name: "Preview change" }).click();
    const reductionPreview = page.getByLabel("Change preview");
    await expect(reductionPreview.getByText("Needs review")).toBeVisible();
    const clientRequestId = await reductionPreview
      .locator('input[name="client_request_id"]')
      .inputValue();
    await reductionPreview.getByRole("button", { name: "Confirm this change" }).click();
    await expect(page.getByText(adminStatus("pending_admin"), { exact: true })).toBeVisible();
    const matchingRequests = (await readRequests()).filter(
      (request) => request.client_request_id === clientRequestId,
    );
    expect(matchingRequests).toHaveLength(1);
    const request = matchingRequests[0];
    if (!request) throw new Error("The confirmed campaign change request is missing.");
    expect(request.campaign_id).toBe(campaignId);
    expect(request.status).toBe("pending_admin");
    expect(request.id).toMatch(/^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i);

    await login(page, ADMIN, "admin");
    await page.goto(`/admin/campaigns/${campaignId}#overview`);
    const changeForm = page.locator("form").filter({
      has: page.locator(`input[name="request_id"][value="${request.id}"]`),
    });
    await expect(changeForm).toHaveCount(1);
    await expect(changeForm).toBeVisible();
    await changeForm.getByLabel("Campaign change decision reason").fill(decisionReason);
    const approvalResponse = page.waitForResponse(
      (response) =>
        response.request().method() === "POST" &&
        new URL(response.url()).pathname === `/admin/campaigns/${campaignId}`,
    );
    await changeForm.getByRole("button", { name: "Approve change" }).click();
    const response = await approvalResponse;
    expect(response.ok(), "the browser approval action must complete successfully").toBe(true);
    await response.finished();
    await expect(changeForm).toHaveCount(0);

    await login(page, ADVERTISER, "advertiser");
    await page.goto(`/advertiser/campaigns/${campaignId}`);
    const decidedRequest = page.getByRole("listitem").filter({
      hasText: `Decision: ${decisionReason}`,
    });
    await expect(decidedRequest).toHaveCount(1);
    await expect(decidedRequest.getByText(`Decision: ${decisionReason}`)).toBeVisible();
    await expect(decidedRequest.getByText("Applied", { exact: true })).toBeVisible();
    const persistedRequests = (await readRequests()).filter((item) => item.id === request.id);
    expect(persistedRequests).toHaveLength(1);
    const persistedRequest = persistedRequests[0];
    if (!persistedRequest) throw new Error("The reviewed campaign change request is missing.");
    expect(persistedRequest).toMatchObject({
      campaign_id: campaignId,
      client_request_id: clientRequestId,
      status: "applied",
      review_reason: decisionReason,
    });
    expect(persistedRequest.reviewed_by_user_id).toBeTruthy();
    expect(persistedRequest.reviewed_by_user_id).not.toBe(request.requested_by_user_id);
  } finally {
    cleanupIsolatedCampaign(campaignId);
  }
});
