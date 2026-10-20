import { beforeEach, expect, it, vi } from "vitest";
import { ApiError } from "@/lib/api/errors";
const mocks = vi.hoisted(() => ({
  role: vi.fn(),
  get: vi.fn(),
  cancel: vi.fn(),
  revalidate: vi.fn(),
  redirect: vi.fn(),
}));
vi.mock("next/cache", () => ({ revalidatePath: mocks.revalidate }));
vi.mock("next/navigation", () => ({ redirect: mocks.redirect }));
vi.mock("@/lib/auth/current-user", () => ({ requireRole: mocks.role }));
vi.mock("@/lib/auth/session", () => ({ getSessionToken: async () => "session" }));
vi.mock("@/lib/api/client", () => ({ createApiClient: () => ({ GET: mocks.get }) }));
vi.mock("@/lib/api/audit-batch2", () => ({ cancelCampaignAsStaff: mocks.cancel }));
import { cancelWholeCampaign } from "./cancellation-actions";
const campaignId = "00000000-0000-4000-8000-000000000001";
const requestId = "00000000-0000-4000-8000-000000000002";
const complaintId = "00000000-0000-4000-8000-000000000003";
const input = { campaignId, requestId, reason: " Owner requested cancellation " };
const campaign = { id: campaignId, organization_id: "organisation", status: "active" };
const complaint = {
  id: complaintId,
  category: "campaign_cancellation",
  reference_type: "campaign",
  reference_id: campaignId,
  advertiser_organization_id: "organisation",
};
beforeEach(() => {
  vi.resetAllMocks();
  mocks.get.mockImplementation(async (path: string) => ({
    data: path.includes("complaints") ? complaint : campaign,
  }));
  mocks.cancel.mockResolvedValue({
    data: { campaign_id: campaignId, cutoff_at: "2026-10-19T10:00:00Z" },
  });
  mocks.redirect.mockImplementation((path: string) => {
    throw new Error(`redirect:${path}`);
  });
});
it("requires staff and submits the trimmed reason with stable identity to the existing financial engine", async () => {
  expect(await cancelWholeCampaign(input)).toHaveProperty(
    "done",
    "Campaign cancelled. Review billing for any settlement.",
  );
  expect(mocks.role).toHaveBeenCalledWith("admin");
  expect(mocks.cancel).toHaveBeenCalledWith(expect.anything(), campaignId, {
    reason: "Owner requested cancellation",
    clientRequestId: requestId,
    complaintId: undefined,
  });
});
it("checks a thread belongs to the same campaign and company before linking it", async () => {
  expect(await cancelWholeCampaign({ ...input, complaintId })).toHaveProperty("done");
  expect(mocks.cancel).toHaveBeenCalledWith(
    expect.anything(),
    campaignId,
    expect.objectContaining({ complaintId }),
  );
});
it.each([
  { category: "campaign_or_job" },
  { reference_type: "job" },
  { reference_id: requestId },
  { advertiser_organization_id: "another company" },
  { id: requestId },
])("rejects a forged/non-cancellation thread: %j", async (difference) => {
  mocks.get.mockImplementation(async (path: string) => ({
    data: path.includes("complaints") ? { ...complaint, ...difference } : campaign,
  }));
  expect(await cancelWholeCampaign({ ...input, complaintId })).toHaveProperty("error");
  expect(mocks.cancel).not.toHaveBeenCalled();
});
it.each(["", "   ", "a".repeat(1001)])(
  "rejects invalid reasons without reads or writes",
  async (reason) => {
    expect(await cancelWholeCampaign({ ...input, reason })).toHaveProperty("error");
    expect(mocks.get).not.toHaveBeenCalled();
    expect(mocks.cancel).not.toHaveBeenCalled();
  },
);
it("accepts the maximum reason length", async () => {
  expect(await cancelWholeCampaign({ ...input, reason: "a".repeat(1000) })).toHaveProperty("done");
});
it("does not cancel a different returned campaign", async () => {
  mocks.get.mockResolvedValue({ data: { ...campaign, id: requestId } });
  expect(await cancelWholeCampaign(input)).toHaveProperty("error");
  expect(mocks.cancel).not.toHaveBeenCalled();
});
it("truthfully recognises an already-cancelled campaign without a second cutoff", async () => {
  mocks.get.mockResolvedValue({ data: { ...campaign, status: "cancelled" } });
  expect(await cancelWholeCampaign(input)).toHaveProperty(
    "done",
    "This campaign has already been cancelled. Review billing for any settlement.",
  );
  expect(mocks.cancel).not.toHaveBeenCalled();
});
it("still rejects a foreign request when the campaign is already cancelled", async () => {
  mocks.get.mockImplementation(async (path: string) => ({
    data: path.includes("complaints")
      ? { ...complaint, reference_id: requestId }
      : { ...campaign, status: "cancelled" },
  }));
  expect(await cancelWholeCampaign({ ...input, complaintId })).toHaveProperty("error");
  expect(mocks.cancel).not.toHaveBeenCalled();
});
it("reuses caller identity after a lost response without claiming success", async () => {
  mocks.cancel.mockRejectedValueOnce(new Error("response lost"));
  expect(await cancelWholeCampaign(input)).toHaveProperty("error");
  expect(mocks.revalidate).not.toHaveBeenCalled();
  expect(await cancelWholeCampaign(input)).toHaveProperty("done");
  expect(mocks.cancel.mock.calls.map((call) => call[2].clientRequestId)).toEqual([
    requestId,
    requestId,
  ]);
});
it.each([
  undefined,
  { campaign_id: requestId, cutoff_at: "2026-10-19T10:00:00Z" },
  { campaign_id: campaignId, cutoff_at: "bad" },
])("does not claim success from malformed confirmation", async (data) => {
  mocks.cancel.mockResolvedValue({ data });
  expect(await cancelWholeCampaign(input)).toHaveProperty("error");
  expect(mocks.revalidate).not.toHaveBeenCalled();
});
it.each([403, 404, 409, 503])("does not expose internal cancellation errors %s", async (status) => {
  mocks.cancel.mockRejectedValue(
    new ApiError(status, { code: "UNAVAILABLE", message: "private financial details" }),
  );
  const state = await cancelWholeCampaign(input);
  expect(state.error).toBeTruthy();
  expect(JSON.stringify(state)).not.toContain("private financial details");
});
it("redirects an expired session", async () => {
  mocks.cancel.mockRejectedValue(new ApiError(401, { code: "EXPIRED", message: "expired" }));
  await expect(cancelWholeCampaign(input)).rejects.toThrow("redirect:/login");
});
