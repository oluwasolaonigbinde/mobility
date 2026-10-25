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
    effective_from: new Date(Date.now() + 86_400_000).toISOString().slice(0, 16),
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
      reason: "synthetic",
    });
    expect(request.body).not.toHaveProperty("campaign_id");
    expect(Object.keys(request.body).sort()).toEqual([
      "daily_rate_naira",
      "daily_target_miles",
      "effective_from",
      "reason",
    ]);
    expect(mocks.revalidatePath).toHaveBeenCalledWith("/admin/campaigns");
  });

  it("refuses invalid input without calling the API and keeps what was typed", async () => {
    const result = await publishDailyRateAction({}, form({ daily_target_miles: "" }));
    expect(result.field).toBe("daily_target_miles");
    expect(result.values?.daily_rate_naira).toBe("10000");
    expect(mocks.post).not.toHaveBeenCalled();
  });

  it("hides arbitrary refusal text and preserves entered values without claiming publication", async () => {
    mocks.post.mockRejectedValueOnce(
      new ApiError(400, {
        code: "INVALID_PAYOUT_RULE_REVISION",
        message: "private rule validation and account detail",
      }),
    );
    const input = form();
    expect(await publishDailyRateAction({}, input)).toEqual({
      error: "The request could not be completed. Check the details and try again.",
      values: Object.fromEntries(input.entries()),
    });

    mocks.post.mockRejectedValueOnce(new Error("socket hang up"));
    expect(await publishDailyRateAction({}, input)).toEqual({
      error: "Could not reach the server. Try again.",
      values: Object.fromEntries(input.entries()),
    });
    expect(mocks.revalidatePath).not.toHaveBeenCalled();
  });
});
