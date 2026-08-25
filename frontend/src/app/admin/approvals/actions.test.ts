import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "@/lib/api/errors";

const mocks = vi.hoisted(() => ({
  post: vi.fn(),
  revalidatePath: vi.fn(),
}));

vi.mock("next/cache", () => ({ revalidatePath: mocks.revalidatePath }));
vi.mock("@/lib/auth/session", () => ({ getSessionToken: vi.fn(async () => "token") }));
vi.mock("@/lib/api/client", () => ({ createApiClient: () => ({ POST: mocks.post }) }));

import { reviewCampaignAction } from "./actions";

const CAMPAIGN_ID = "00000000-0000-4000-8000-00000000000a";

function reviewForm(intent: "approve" | "reject", reason = ""): FormData {
  const form = new FormData();
  form.set("campaign_id", CAMPAIGN_ID);
  form.set("intent", intent);
  form.set("reason", reason);
  return form;
}

describe("reviewCampaignAction", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.post.mockResolvedValue({ data: {} });
  });

  it("approves only through the dedicated admin endpoint", async () => {
    await expect(reviewCampaignAction({}, reviewForm("approve"))).resolves.toEqual({
      done: "Campaign approved",
    });
    expect(mocks.post).toHaveBeenCalledWith("/api/v1/admin/campaigns/{campaign_id}/approve", {
      params: { path: { campaign_id: CAMPAIGN_ID } },
    });
    expect(mocks.revalidatePath).toHaveBeenCalledWith("/admin/approvals");
  });

  it("requires and trims a rejection reason before using the dedicated endpoint", async () => {
    await expect(reviewCampaignAction({}, reviewForm("reject", "   "))).resolves.toEqual({
      error: "A rejection reason is required",
    });
    expect(mocks.post).not.toHaveBeenCalled();

    await expect(
      reviewCampaignAction({}, reviewForm("reject", "  Revise the legal copy.  ")),
    ).resolves.toEqual({
      done: "Campaign rejected",
    });
    expect(mocks.post).toHaveBeenCalledWith("/api/v1/admin/campaigns/{campaign_id}/reject", {
      params: { path: { campaign_id: CAMPAIGN_ID } },
      body: { reason: "Revise the legal copy." },
    });
  });

  it("surfaces a stable lost-transition error without refreshing", async () => {
    mocks.post.mockRejectedValue(
      new ApiError(409, {
        code: "CAMPAIGN_REVIEW_STATE_CONFLICT",
        message: "Campaign review state changed. Refresh and try again.",
      }),
    );

    await expect(reviewCampaignAction({}, reviewForm("approve"))).resolves.toEqual({
      error: "Campaign review state changed. Refresh and try again.",
    });
    expect(mocks.revalidatePath).not.toHaveBeenCalled();
  });
});
