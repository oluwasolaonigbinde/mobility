import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  post: vi.fn(),
  redirect: vi.fn(),
  revalidatePath: vi.fn(),
}));

vi.mock("next/cache", () => ({ revalidatePath: mocks.revalidatePath }));
vi.mock("next/navigation", () => ({ redirect: mocks.redirect }));
vi.mock("@/lib/auth/session", () => ({ getSessionToken: vi.fn(async () => "token") }));
vi.mock("@/lib/api/client", () => ({ createApiClient: () => ({ POST: mocks.post }) }));

import { createCampaignAction } from "./actions";

const CAMPAIGN_ID = "00000000-0000-4000-8000-00000000000a";

describe("createCampaignAction", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.post.mockResolvedValue({ data: { id: CAMPAIGN_ID } });
  });

  it("always creates campaigns as drafts", async () => {
    await createCampaignAction({
      basics: {
        name: "Draft-only campaign",
        description: "",
        start_at: "",
        end_at: "",
        budget_amount: "",
        daily_budget_amount: "",
      },
      creatives: [],
    });

    expect(mocks.post).toHaveBeenCalledWith("/api/v1/advertiser/campaigns", {
      body: {
        name: "Draft-only campaign",
        description: null,
        status: "draft",
        start_at: null,
        end_at: null,
        budget_amount: null,
        daily_budget_amount: null,
      },
    });
    expect(mocks.revalidatePath).toHaveBeenCalledWith("/advertiser/campaigns");
    expect(mocks.redirect).toHaveBeenCalledWith(`/advertiser/campaigns/${CAMPAIGN_ID}`);
  });
});
