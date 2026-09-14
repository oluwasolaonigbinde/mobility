import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "@/lib/api/errors";

const mocks = vi.hoisted(() => ({
  patch: vi.fn(),
  post: vi.fn(),
  revalidatePath: vi.fn(),
}));

vi.mock("next/cache", () => ({ revalidatePath: mocks.revalidatePath }));
vi.mock("@/lib/auth/session", () => ({ getSessionToken: vi.fn(async () => "token") }));
vi.mock("@/lib/api/client", () => ({
  createApiClient: () => ({ PATCH: mocks.patch, POST: mocks.post }),
}));

import {
  confirmCampaignChangeAction,
  previewCampaignChangeAction,
  replaceCreativeAndSubmitAction,
  requestCampaignCancellationAction,
  submitCampaignForReviewAction,
  submitCreativeForReviewAction,
} from "./actions";

const CAMPAIGN_ID = "00000000-0000-4000-8000-00000000000a";
const CREATIVE_ID = "00000000-0000-4000-8000-00000000000b";
const CHANGE_REQUEST_ID = "00000000-0000-4000-8000-00000000000c";
const CANCELLATION_REQUEST_ID = "00000000-0000-4000-8000-00000000000d";

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
      error: "The campaign state changed. Refresh and try again.",
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
      error: "The creative state changed. Refresh and try again.",
    });
  });
});

describe("replaceCreativeAndSubmitAction", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.patch.mockResolvedValue({ data: {} });
    mocks.post.mockResolvedValue({ data: {} });
  });

  it("replaces the managed file before submitting the same creative", async () => {
    const form = creativeSubmitForm();
    form.set("stored_file_id", "00000000-0000-4000-8000-000000000099");
    form.set("creative_type", "image");

    await expect(replaceCreativeAndSubmitAction({}, form)).resolves.toEqual({
      done: "Replacement artwork submitted for admin review.",
    });
    expect(mocks.patch).toHaveBeenCalledWith(
      "/api/v1/advertiser/campaigns/{campaign_id}/creatives/{creative_id}",
      {
        params: { path: { campaign_id: CAMPAIGN_ID, creative_id: CREATIVE_ID } },
        body: {
          stored_file_id: "00000000-0000-4000-8000-000000000099",
          creative_type: "image",
        },
      },
    );
    expect(mocks.post).toHaveBeenCalledTimes(1);
  });

  it("keeps backend details out of an unknown replacement result", async () => {
    mocks.post.mockRejectedValueOnce(
      new ApiError(500, { code: "INTERNAL", message: "postgres secret.internal" }),
    );
    const form = creativeSubmitForm();
    form.set("stored_file_id", "00000000-0000-4000-8000-000000000099");
    form.set("creative_type", "image");
    const result = await replaceCreativeAndSubmitAction({}, form);
    expect(result.error).not.toContain("postgres");
    expect(result.error).not.toContain("secret.internal");
  });
});

describe("campaign change preview and confirmation", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.post.mockResolvedValue({ data: {} });
  });

  it("previews without a client mutation identity, then confirms the exact digest-bound inputs", async () => {
    mocks.post.mockResolvedValueOnce({
      data: {
        before: { budget_amount: "1000.00" },
        after: { budget_amount: "1200.00" },
        source_sha256: "a".repeat(64),
        preview_sha256: "b".repeat(64),
        classifications: ["expansion"],
        requested_liability_amount: "0.00",
        available_liability_amount: "0.00",
        currency: "NGN",
        outcome: "apply_now",
      },
    });
    const form = submitForm();
    form.set("client_request_id", CHANGE_REQUEST_ID);
    form.set("budget_amount", "1200.00");
    form.set("end_at", "2026-09-30T18:00");
    form.set("reason", "  Extend the approved campaign scope  ");

    const preview = await previewCampaignChangeAction({}, form);
    expect(preview.preview?.preview_sha256).toBe("b".repeat(64));
    expect(mocks.post).toHaveBeenCalledWith(
      "/api/v1/advertiser/campaigns/{campaign_id}/change-preview",
      {
        params: { path: { campaign_id: CAMPAIGN_ID } },
        body: {
          budget_amount: "1200.00",
          end_at: "2026-09-30T17:00:00.000Z",
          reason: "Extend the approved campaign scope",
        },
      },
    );

    form.set("source_sha256", "a".repeat(64));
    form.set("preview_sha256", "b".repeat(64));
    await expect(confirmCampaignChangeAction({}, form)).resolves.toMatchObject({
      done: "Campaign change confirmed.",
      confirmedRequest: {},
    });
    expect(mocks.post).toHaveBeenLastCalledWith(
      "/api/v1/advertiser/campaigns/{campaign_id}/change-requests",
      {
        params: { path: { campaign_id: CAMPAIGN_ID } },
        body: {
          client_request_id: CHANGE_REQUEST_ID,
          source_sha256: "a".repeat(64),
          preview_sha256: "b".repeat(64),
          budget_amount: "1200.00",
          end_at: "2026-09-30T17:00:00.000Z",
          reason: "Extend the approved campaign scope",
        },
      },
    );
    expect(mocks.revalidatePath).not.toHaveBeenCalledWith(`/advertiser/campaigns/${CAMPAIGN_ID}`);
    expect(mocks.revalidatePath).toHaveBeenCalledWith("/admin/approvals");
  });

  it("rejects an empty change or missing reason before calling the API", async () => {
    const form = submitForm();
    form.set("client_request_id", CHANGE_REQUEST_ID);
    await expect(previewCampaignChangeAction({}, form)).resolves.toEqual({
      error: "A reason is required",
    });
    expect(mocks.post).not.toHaveBeenCalled();
  });

  it("never returns raw backend text for stale or unknown confirmation failures", async () => {
    const form = submitForm();
    form.set("client_request_id", CHANGE_REQUEST_ID);
    form.set("budget_amount", "1200.00");
    form.set("reason", "Confirm exact change");
    form.set("source_sha256", "a".repeat(64));
    form.set("preview_sha256", "b".repeat(64));
    mocks.post.mockRejectedValue(
      new ApiError(409, {
        code: "CAMPAIGN_CHANGE_STALE",
        message: "PRIVATE database value",
      }),
    );
    const result = await confirmCampaignChangeAction({}, form);
    expect(result).toEqual({ error: "Campaign details changed. Preview the change again." });
    expect(JSON.stringify(result)).not.toContain("PRIVATE");
  });
});

describe("requestCampaignCancellationAction", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.post.mockResolvedValue({ data: {} });
  });

  function cancellationForm({ confirmed = true } = {}): FormData {
    const form = submitForm();
    form.set("client_request_id", CANCELLATION_REQUEST_ID);
    form.set("reason", "  Advertiser ended the campaign  ");
    if (confirmed) form.set("confirmed", "on");
    return form;
  }

  it("uses one exact retry identity and refreshes advertiser campaign views", async () => {
    await expect(requestCampaignCancellationAction({}, cancellationForm())).resolves.toEqual({
      done: "Campaign cancelled at the recorded financial cutoff.",
    });
    expect(mocks.post).toHaveBeenCalledWith("/api/v1/advertiser/campaigns/{campaign_id}/cancel", {
      params: { path: { campaign_id: CAMPAIGN_ID } },
      body: {
        client_request_id: CANCELLATION_REQUEST_ID,
        reason: "Advertiser ended the campaign",
      },
    });
    expect(mocks.revalidatePath).toHaveBeenCalledWith(`/advertiser/campaigns/${CAMPAIGN_ID}`);
    expect(mocks.revalidatePath).toHaveBeenCalledWith("/advertiser/campaigns");
  });

  it("fails before the API when permanent cancellation is not confirmed", async () => {
    await expect(
      requestCampaignCancellationAction({}, cancellationForm({ confirmed: false })),
    ).resolves.toEqual({
      error: "Confirm that you understand cancellation is permanent",
    });
    expect(mocks.post).not.toHaveBeenCalled();
  });
});
