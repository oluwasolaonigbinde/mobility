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

  it("binds creatives by managed file id and never sends a browser URL", async () => {
    await createCampaignAction({
      basics: {
        name: "Managed campaign",
        description: "",
        start_at: "",
        end_at: "",
        budget_amount: "",
        daily_budget_amount: "",
      },
      creatives: [
        {
          name: "Wrap",
          creative_type: "image",
          placement: "vehicle_exterior",
          stored_file_id: "00000000-0000-4000-8000-000000000001",
          original_filename: "wrap.png",
        },
      ],
    });

    expect(mocks.post).toHaveBeenNthCalledWith(
      2,
      "/api/v1/advertiser/campaigns/{campaign_id}/creatives",
      {
        params: { path: { campaign_id: CAMPAIGN_ID } },
        body: {
          name: "Wrap",
          creative_type: "image",
          placement: "vehicle_exterior",
          stored_file_id: "00000000-0000-4000-8000-000000000001",
          status: "draft",
        },
      },
    );
  });
});

it("retries attachments against the created campaign without creating another", async () => {
  mocks.post.mockReset();
  mocks.post
    .mockResolvedValueOnce({ data: { id: CAMPAIGN_ID } })
    .mockRejectedValueOnce(new Error("lost attachment response"));
  const input = {
    basics: {
      name: "Recover me",
      description: "",
      start_at: "",
      end_at: "",
      budget_amount: "",
      daily_budget_amount: "",
    },
    creatives: [
      {
        name: "Wrap",
        creative_type: "image" as const,
        placement: "vehicle_exterior" as const,
        stored_file_id: "00000000-0000-4000-8000-000000000001",
        original_filename: "wrap.png",
      },
    ],
  };
  const state = await createCampaignAction(input);
  expect(state.createdCampaignId).toBe(CAMPAIGN_ID);
  mocks.post.mockResolvedValue({ data: { id: "creative" } });
  await createCampaignAction(input, state.createdCampaignId);
  expect(
    mocks.post.mock.calls.filter(([path]) => path === "/api/v1/advertiser/campaigns"),
  ).toHaveLength(1);
  expect(mocks.post.mock.calls.at(-1)?.[1].params.path.campaign_id).toBe(CAMPAIGN_ID);
});

it("rejects an invalid recovery target before any API mutation", async () => {
  mocks.post.mockReset();
  const result = await createCampaignAction(
    {
      basics: {
        name: "Name",
        description: "",
        start_at: "",
        end_at: "",
        budget_amount: "",
        daily_budget_amount: "",
      },
      creatives: [],
    },
    "not-an-id",
  );
  expect(result.error).toBeTruthy();
  expect(mocks.post).not.toHaveBeenCalled();
});
