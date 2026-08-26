import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "@/lib/api/errors";

const mocks = vi.hoisted(() => ({
  post: vi.fn(),
  revalidatePath: vi.fn(),
}));

vi.mock("next/cache", () => ({ revalidatePath: mocks.revalidatePath }));
vi.mock("@/lib/auth/session", () => ({ getSessionToken: vi.fn(async () => "token") }));
vi.mock("@/lib/api/client", () => ({ createApiClient: () => ({ POST: mocks.post }) }));

import { submitCampaignForReviewAction, submitCreativeForReviewAction } from "./actions";

const CAMPAIGN_ID = "00000000-0000-4000-8000-00000000000a";
const CREATIVE_ID = "00000000-0000-4000-8000-00000000000b";

function submitForm(campaignId = CAMPAIGN_ID): FormData {
  const form = new FormData();
  form.set("campaign_id", campaignId);
  return form;
}

function creativeSubmitForm(campaignId = CAMPAIGN_ID, creativeId = CREATIVE_ID): FormData {
  const form = new FormData();
  form.set("campaign_id", campaignId);
  form.set("creative_id", creativeId);
  return form;
}

describe("submitCampaignForReviewAction", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.post.mockResolvedValue({ data: {} });
  });

  it("uses the dedicated advertiser submit endpoint and refreshes campaign views", async () => {
    await expect(submitCampaignForReviewAction({}, submitForm())).resolves.toEqual({
      done: "Campaign submitted for admin review.",
    });
    expect(mocks.post).toHaveBeenCalledWith("/api/v1/advertiser/campaigns/{campaign_id}/submit", {
      params: { path: { campaign_id: CAMPAIGN_ID } },
    });
    expect(mocks.revalidatePath).toHaveBeenCalledWith(`/advertiser/campaigns/${CAMPAIGN_ID}`);
    expect(mocks.revalidatePath).toHaveBeenCalledWith("/advertiser/campaigns");
  });

  it("does not submit malformed campaign identifiers", async () => {
    await expect(submitCampaignForReviewAction({}, submitForm("not-a-uuid"))).resolves.toEqual({
      error: "Invalid campaign review request.",
    });
    expect(mocks.post).not.toHaveBeenCalled();
  });

  it("shows the stable review conflict returned by the API", async () => {
    mocks.post.mockRejectedValue(
      new ApiError(409, {
        code: "CAMPAIGN_REVIEW_STATE_CONFLICT",
        message: "Campaign review state changed. Refresh and try again.",
      }),
    );

    await expect(submitCampaignForReviewAction({}, submitForm())).resolves.toEqual({
      error: "Campaign review state changed. Refresh and try again.",
    });
  });
});

describe("submitCreativeForReviewAction", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.post.mockResolvedValue({ data: {} });
  });

  it("uses the dedicated creative submit endpoint and refreshes both role surfaces", async () => {
    await expect(submitCreativeForReviewAction({}, creativeSubmitForm())).resolves.toEqual({
      done: "Creative submitted for admin review.",
    });
    expect(mocks.post).toHaveBeenCalledWith(
      "/api/v1/advertiser/campaigns/{campaign_id}/creatives/{creative_id}/submit",
      {
        params: {
          path: { campaign_id: CAMPAIGN_ID, creative_id: CREATIVE_ID },
        },
      },
    );
    expect(mocks.revalidatePath).toHaveBeenCalledWith(`/advertiser/campaigns/${CAMPAIGN_ID}`);
    expect(mocks.revalidatePath).toHaveBeenCalledWith("/admin/approvals");
  });

  it("does not submit malformed creative identifiers", async () => {
    await expect(
      submitCreativeForReviewAction({}, creativeSubmitForm(CAMPAIGN_ID, "not-a-uuid")),
    ).resolves.toEqual({ error: "Invalid creative review request." });
    expect(mocks.post).not.toHaveBeenCalled();
  });

  it("shows the stable creative review conflict returned by the API", async () => {
    mocks.post.mockRejectedValue(
      new ApiError(409, {
        code: "CREATIVE_REVIEW_STATE_CONFLICT",
        message: "Creative review state does not allow this operation",
      }),
    );

    await expect(submitCreativeForReviewAction({}, creativeSubmitForm())).resolves.toEqual({
      error: "Creative review state does not allow this operation",
    });
  });
});
