import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "@/lib/api/errors";

const mocks = vi.hoisted(() => ({ post: vi.fn(), revalidatePath: vi.fn() }));
vi.mock("@/lib/api/client", () => ({ createApiClient: () => ({ POST: mocks.post }) }));
vi.mock("@/lib/auth/session", () => ({ getSessionToken: vi.fn(async () => "token") }));
vi.mock("next/cache", () => ({ revalidatePath: mocks.revalidatePath }));

import { publishDailyRateAction } from "./actions";

const CAMPAIGN_ID = "7f9c1f4e-8a5b-4c3d-9e2f-1a2b3c4d5e6f";

function form(overrides: Record<string, string> = {}): FormData {
  const values: Record<string, string> = {
    campaign_id: CAMPAIGN_ID,
    daily_rate_naira: "10000",
    daily_target_miles: "70",
    shortfall_strategy: "per_mile_deduction",
    deduction_per_mile_naira: "140",
    minimum_miles: "0",
    outside_area_weight: "0.5",
    effective_from: new Date(Date.now() + 3_600_000).toISOString().slice(0, 16),
    reason: "synthetic",
    ...overrides,
  };
  const data = new FormData();
  for (const [key, value] of Object.entries(values)) data.set(key, value);
  return data;
}

describe("publishDailyRateAction", () => {
  beforeEach(() => vi.clearAllMocks());

  it("posts exactly the entered values and revalidates", async () => {
    mocks.post.mockResolvedValueOnce({ data: {} });
    expect(await publishDailyRateAction({}, form())).toEqual({ created: true });
    const [path, request] = mocks.post.mock.calls[0]!;
    expect(path).toBe("/api/v1/admin/campaigns/{campaign_id}/payout-v4-revisions");
    expect(request.params.path.campaign_id).toBe(CAMPAIGN_ID);
    expect(request.body).toMatchObject({
      daily_rate_naira: "10000",
      daily_target_miles: "70",
      shortfall_strategy: "per_mile_deduction",
      deduction_per_mile_naira: "140",
      minimum_miles: "0",
      outside_area_weight: "0.5",
      reason: "synthetic",
    });
    expect(request.body).not.toHaveProperty("campaign_id");
    expect(mocks.revalidatePath).toHaveBeenCalledWith("/admin/payouts/rules");
  });

  it("refuses invalid input without calling the API and keeps what was typed", async () => {
    const result = await publishDailyRateAction({}, form({ deduction_per_mile_naira: "" }));
    expect(result.field).toBe("deduction_per_mile_naira");
    expect(result.values?.daily_rate_naira).toBe("10000");
    expect(mocks.post).not.toHaveBeenCalled();
  });

  it("maps the switched-off 503, other refusals and network failure", async () => {
    mocks.post.mockRejectedValueOnce(
      new ApiError(503, { code: "PAYOUT_V4_POLICY_UNAVAILABLE", message: "off" }),
    );
    expect(await publishDailyRateAction({}, form())).toMatchObject({ notSwitchedOn: true });

    mocks.post.mockRejectedValueOnce(
      new ApiError(400, { code: "INVALID_PAYOUT_RULE_REVISION", message: "must be later" }),
    );
    expect(await publishDailyRateAction({}, form())).toMatchObject({ error: "must be later" });

    mocks.post.mockRejectedValueOnce(new Error("socket hang up"));
    const failed = await publishDailyRateAction({}, form());
    expect(failed.error).toBe("Could not reach the server. Try again.");
    expect(mocks.revalidatePath).not.toHaveBeenCalled();
  });
});
