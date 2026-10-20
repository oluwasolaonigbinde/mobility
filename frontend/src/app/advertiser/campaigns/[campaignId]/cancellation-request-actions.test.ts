import { beforeEach, expect, it, vi } from "vitest";
import { ApiError } from "@/lib/api/errors";
const mocks = vi.hoisted(() => ({
  role: vi.fn(),
  get: vi.fn(),
  request: vi.fn(),
  revalidate: vi.fn(),
  redirect: vi.fn(),
}));
vi.mock("next/cache", () => ({ revalidatePath: mocks.revalidate }));
vi.mock("next/navigation", () => ({ redirect: mocks.redirect }));
vi.mock("@/lib/auth/current-user", () => ({ requireRole: mocks.role }));
vi.mock("@/lib/auth/session", () => ({ getSessionToken: async () => "session" }));
vi.mock("@/lib/api/client", () => ({ createApiClient: () => ({ GET: mocks.get }) }));
vi.mock("@/lib/api/audit-batch2", () => ({ askTerraxToCancelCampaign: mocks.request }));
import { requestCampaignCancellation } from "./cancellation-request-actions";
const campaign = "00000000-0000-4000-8000-000000000001";
const requestId = "00000000-0000-4000-8000-000000000002";
const thread = "00000000-0000-4000-8000-000000000003";
beforeEach(() => {
  vi.resetAllMocks();
  mocks.get.mockResolvedValue({ data: { id: campaign } });
  mocks.request.mockResolvedValue({ data: { id: thread, category: "campaign_cancellation" } });
  mocks.redirect.mockImplementation((path: string) => {
    throw new Error(`redirect:${path}`);
  });
});
it("reauthorises the campaign, trims the reason and returns only a confirmed cancellation conversation", async () => {
  expect(
    await requestCampaignCancellation(campaign, " Please stop this campaign ", requestId),
  ).toEqual({ threadId: thread });
  expect(mocks.role).toHaveBeenCalledWith("advertiser");
  expect(mocks.get).toHaveBeenCalledWith("/api/v1/advertiser/campaigns/{campaign_id}", {
    params: { path: { campaign_id: campaign } },
  });
  expect(mocks.request).toHaveBeenCalledWith(
    expect.anything(),
    campaign,
    "Please stop this campaign",
    requestId,
  );
  expect(mocks.revalidate).toHaveBeenCalledWith(`/advertiser/campaigns/${campaign}`);
});
it.each(["", "   ", "a".repeat(2001)])(
  "rejects an invalid reason without reads or writes",
  async (reason) => {
    expect(await requestCampaignCancellation(campaign, reason, requestId)).toHaveProperty("error");
    expect(mocks.get).not.toHaveBeenCalled();
    expect(mocks.request).not.toHaveBeenCalled();
  },
);
it.each([
  ["invalid", requestId],
  [campaign, "invalid"],
])("rejects forged malformed route/request IDs", async (id, key) => {
  expect(await requestCampaignCancellation(id, "Reason", key)).toHaveProperty("error");
  expect(mocks.request).not.toHaveBeenCalled();
});
it("does not write for a foreign campaign response", async () => {
  mocks.get.mockResolvedValue({ data: { id: thread } });
  expect(await requestCampaignCancellation(campaign, "Reason", requestId)).toHaveProperty("error");
  expect(mocks.request).not.toHaveBeenCalled();
});
it.each([403, 404])("keeps denied campaign errors private: %s", async (status) => {
  mocks.get.mockRejectedValue(new ApiError(status, { code: "DENIED", message: "private company" }));
  const result = await requestCampaignCancellation(campaign, "Reason", requestId);
  expect(result.error).toBeTruthy();
  expect(JSON.stringify(result)).not.toContain("private company");
  expect(mocks.request).not.toHaveBeenCalled();
});
it("redirects an expired session rather than prompting repeated submission", async () => {
  mocks.request.mockRejectedValue(new ApiError(401, { code: "EXPIRED", message: "expired" }));
  await expect(requestCampaignCancellation(campaign, "Reason", requestId)).rejects.toThrow(
    "redirect:/login",
  );
});
it.each([
  undefined,
  { id: thread, category: "campaign_or_job" },
  { id: "bad", category: "campaign_cancellation" },
])("does not report success for an incomplete or wrong-kind response", async (data) => {
  mocks.request.mockResolvedValue({ data });
  expect(await requestCampaignCancellation(campaign, "Reason", requestId)).toHaveProperty("error");
  expect(mocks.revalidate).not.toHaveBeenCalled();
});
it("keeps the same caller request identity on an ambiguous retry", async () => {
  mocks.request.mockRejectedValueOnce(new Error("response lost"));
  expect(await requestCampaignCancellation(campaign, "Reason", requestId)).toHaveProperty("error");
  expect(await requestCampaignCancellation(campaign, "Reason", requestId)).toEqual({
    threadId: thread,
  });
  expect(mocks.request.mock.calls.map((call) => call[3])).toEqual([requestId, requestId]);
});
