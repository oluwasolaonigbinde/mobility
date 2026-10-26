import { expect, test, type Page } from "@playwright/test";
import {
  cleanupIsolatedCampaign,
  createIsolatedActiveCampaign,
  psql,
} from "./support/campaign-fixture";
import type { components } from "../src/lib/api/schema";

const ADVERTISER = {
  email: "advertiser@demo.mobility.local",
  password: "DemoAdvertiser12345!",
};

async function login(page: Page, role: "advertiser" | "admin" = "advertiser") {
  await page.context().clearCookies();
  await page.goto("/login");
  await page
    .getByLabel("Email")
    .fill(role === "admin" ? "admin@demo.mobility.local" : ADVERTISER.email);
  await page
    .getByLabel("Password")
    .fill(role === "admin" ? "DemoAdmin12345!" : ADVERTISER.password);
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.waitForURL(`**/${role}`);
}

test("advertiser cancellation request keeps running until staff confirms one cutoff", async ({
  page,
}) => {
  test.setTimeout(60_000);
  const { campaignId, campaignName } = createIsolatedActiveCampaign("E2E cancellation");
  const cutoffCount = () =>
    Number(
      psql(
        "SELECT count(*) FROM campaign_cancellations WHERE campaign_id = :'campaign_id'::uuid;",
        { campaign_id: campaignId },
      )
        .toString("utf8")
        .trim(),
    );
  const apiBase = process.env.E2E_API_BASE_URL ?? "http://localhost:8000";
  const sessionHeaders = async () => {
    const session = (await page.context().cookies()).find(
      (cookie) => cookie.name === (process.env.SESSION_COOKIE_NAME ?? "mobility_session"),
    );
    if (!session) throw new Error("Cancellation proof requires an authenticated session");
    return { Authorization: `Bearer ${session.value}` };
  };
  try {
    await login(page);
    await page.goto("/advertiser/campaigns");
    await page.getByRole("table").getByRole("link", { name: campaignName }).click();
    await page.locator("#manage > summary").click();

    const panel = page.getByRole("region", { name: "Ask Terrax to cancel", exact: true });
    await expect(panel).toBeVisible();
    const request = panel.getByRole("button", { name: "Ask Terrax to cancel", exact: true });
    const reason = panel.getByLabel("Why would you like to cancel?", { exact: true });
    await request.click();
    expect(
      await reason.evaluate(
        (input) => input instanceof HTMLTextAreaElement && input.validity.valueMissing,
      ),
    ).toBe(true);
    await expect(page.getByRole("link", { name: "View cancellation request" })).toHaveCount(0);
    expect(cutoffCount()).toBe(0);
    await reason.fill("Synthetic isolated cancellation journey");
    await request.click();
    await expect(page.getByRole("status", { name: "Cancellation request" })).toContainText(
      "Your campaign continues until Terrax confirms.",
    );
    const conversationHref = await page
      .getByRole("link", { name: "View cancellation request" })
      .getAttribute("href");
    const complaintId = conversationHref?.split("/").at(-1);
    if (!complaintId || !/^[0-9a-f-]{36}$/.test(complaintId))
      throw new Error("The cancellation request is missing");
    const stillRunning = await page.request.get(
      `${apiBase}/api/v1/advertiser/campaigns/${campaignId}`,
      {
        headers: await sessionHeaders(),
      },
    );
    expect(stillRunning.status()).toBe(200);
    expect((await stillRunning.json()).status).toBe("active");
    expect(cutoffCount()).toBe(0);

    await login(page, "admin");
    await page.goto(`/admin/support?complaint=${complaintId}`);
    const drawer = page.getByRole("dialog", { name: "Cancellation request", exact: true });
    const staffPanel = drawer.getByRole("region", { name: "Cancel campaign", exact: true });
    await expect(staffPanel).toBeVisible();
    await staffPanel
      .getByLabel("Reason", { exact: true })
      .fill("Staff confirmed the isolated cancellation request");
    const cancel = staffPanel.getByRole("button", { name: "Cancel campaign", exact: true });
    await cancel.click();
    const confirmation = page.getByRole("alertdialog");
    await expect(confirmation).toContainText(`Cancel ${campaignName}?`);
    await expect(confirmation).toContainText("this does not confirm a refund");
    await confirmation.getByRole("button", { name: "Keep campaign running" }).click();
    expect(cutoffCount()).toBe(0);
    await cancel.click();
    await confirmation.getByRole("button", { name: "Cancel campaign", exact: true }).click();
    await expect.poll(cutoffCount).toBe(1);
    const cancelled = await page.request.get(`${apiBase}/api/v1/admin/campaigns/${campaignId}`, {
      headers: await sessionHeaders(),
    });
    expect(cancelled.status()).toBe(200);
    expect((await cancelled.json()).status).toBe("cancelled");
    expect(cutoffCount()).toBe(1);
    const conversation = await page.request.get(
      `${apiBase}/api/v1/admin/complaints/${complaintId}`,
      {
        headers: await sessionHeaders(),
      },
    );
    expect(conversation.status()).toBe(200);
    const recorded =
      (await conversation.json()) as components["schemas"]["StaffComplaintDetailRead"];
    expect(recorded.reference_id).toBe(campaignId);
    expect(recorded.category).toBe("campaign_cancellation");
    expect(recorded.status).toBe("answered");
    expect(
      recorded.messages.filter(
        (message) =>
          message.author_side === "staff" && message.body === "The campaign has been cancelled.",
      ),
    ).toHaveLength(1);
    await page.reload();
    await expect(
      drawer.getByRole("status").filter({ hasText: "This campaign has already been cancelled." }),
    ).toBeVisible();
    expect(cutoffCount()).toBe(1);

    await login(page);
    await page.goto(`/advertiser/campaigns/${campaignId}`);
    await expect(
      page.getByRole("region", { name: "Next step" }).getByText("Cancelled", { exact: true }),
    ).toBeVisible();
    await expect(
      page.getByRole("region", { name: "Ask Terrax to cancel", exact: true }),
    ).toHaveCount(0);
  } finally {
    cleanupIsolatedCampaign(campaignId);
  }
});
