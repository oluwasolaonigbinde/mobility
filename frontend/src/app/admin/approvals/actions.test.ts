import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "@/lib/api/errors";

const mocks = vi.hoisted(() => ({
  post: vi.fn(),
  revalidatePath: vi.fn(),
}));

vi.mock("next/cache", () => ({ revalidatePath: mocks.revalidatePath }));
vi.mock("@/lib/auth/session", () => ({ getSessionToken: vi.fn(async () => "token") }));
vi.mock("@/lib/api/client", () => ({ createApiClient: () => ({ POST: mocks.post }) }));

import {
  reviewCampaignAction,
  reviewCreativeAction,
  reviewInstallationEvidenceAction,
} from "./actions";

const CAMPAIGN_ID = "00000000-0000-4000-8000-00000000000a";
const CREATIVE_ID = "00000000-0000-4000-8000-00000000000b";
const EVIDENCE_ID = "00000000-0000-4000-8000-00000000000c";

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

describe("reviewCreativeAction", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.post.mockResolvedValue({ data: {} });
  });

  function creativeForm(intent: "approve" | "reject", reason = ""): FormData {
    const form = new FormData();
    form.set("creative_id", CREATIVE_ID);
    form.set("intent", intent);
    form.set("reason", reason);
    return form;
  }

  it("uses the dedicated creative decision endpoints and requires rejection reason", async () => {
    await expect(reviewCreativeAction({}, creativeForm("approve"))).resolves.toEqual({
      done: "Creative approved",
    });
    expect(mocks.post).toHaveBeenCalledWith("/api/v1/admin/creatives/{creative_id}/approve", {
      params: { path: { creative_id: CREATIVE_ID } },
    });

    vi.clearAllMocks();
    await expect(reviewCreativeAction({}, creativeForm("reject", "  "))).resolves.toEqual({
      error: "A rejection reason is required",
    });
    expect(mocks.post).not.toHaveBeenCalled();

    await expect(
      reviewCreativeAction({}, creativeForm("reject", "  Replace the low-resolution asset. ")),
    ).resolves.toEqual({ done: "Creative rejected" });
    expect(mocks.post).toHaveBeenCalledWith("/api/v1/admin/creatives/{creative_id}/reject", {
      params: { path: { creative_id: CREATIVE_ID } },
      body: { reason: "Replace the low-resolution asset." },
    });
    expect(mocks.revalidatePath).toHaveBeenCalledWith("/admin/approvals");
  });
});

describe("reviewInstallationEvidenceAction", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.post.mockResolvedValue({ data: {} });
  });

  function evidenceForm(intent: "approve" | "reject", reason = ""): FormData {
    const form = new FormData();
    form.set("submission_id", EVIDENCE_ID);
    form.set("intent", intent);
    form.set("reason", reason);
    return form;
  }

  it("uses governed evidence decisions and rejects an empty rejection reason", async () => {
    await expect(reviewInstallationEvidenceAction({}, evidenceForm("approve"))).resolves.toEqual({
      done: "Installation approved",
    });
    expect(mocks.post).toHaveBeenCalledWith(
      "/api/v1/admin/installation-evidence/{submission_id}/approve",
      {
        params: { path: { submission_id: EVIDENCE_ID } },
        body: {},
      },
    );

    vi.clearAllMocks();
    await expect(
      reviewInstallationEvidenceAction({}, evidenceForm("reject", "   ")),
    ).resolves.toEqual({ error: "A rejection reason is required" });
    expect(mocks.post).not.toHaveBeenCalled();
  });
});
