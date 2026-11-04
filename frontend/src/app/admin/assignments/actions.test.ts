import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  post: vi.fn(),
  get: vi.fn(),
  revalidatePath: vi.fn(),
}));

vi.mock("next/cache", () => ({ revalidatePath: mocks.revalidatePath }));
vi.mock("@/lib/auth/session", () => ({ getSessionToken: vi.fn(async () => "token") }));
vi.mock("@/lib/api/client", () => ({
  createApiClient: () => ({ POST: mocks.post, GET: mocks.get }),
}));

import { cancelAssignmentAction } from "./actions";

const ASSIGNMENT_ID = "00000000-0000-4000-8000-00000000000a";

describe("cancelAssignmentAction", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.post.mockResolvedValue({ data: {} });
  });

  it("requires and trims the permanent removal reason", async () => {
    await expect(cancelAssignmentAction(ASSIGNMENT_ID, "   ")).resolves.toEqual({
      error: "A cancellation reason is required",
    });
    expect(mocks.post).not.toHaveBeenCalled();

    await expect(
      cancelAssignmentAction(ASSIGNMENT_ID, "  Vehicle removed from campaign scope  "),
    ).resolves.toEqual({});
    expect(mocks.post).toHaveBeenCalledWith(
      "/api/v1/admin/campaign-assignments/{assignment_id}/cancel",
      {
        params: { path: { assignment_id: ASSIGNMENT_ID } },
        body: { reason: "Vehicle removed from campaign scope" },
      },
    );
    expect(mocks.revalidatePath).toHaveBeenCalledWith("/admin/campaigns");
  });
});

import { ApiError } from "@/lib/api/errors";
import { activateAssignmentAction, listAssignmentRecommendationsAction } from "./actions";
describe("job start and recommendation failures", () => {
  beforeEach(() => vi.resetAllMocks());
  it("rejects an invalid job without sending a start", async () => {
    expect(await activateAssignmentAction("invalid")).toEqual({
      error: "Something went wrong. Refresh and try again.",
    });
    expect(mocks.post).not.toHaveBeenCalled();
  });
  it.each([true, false])("keeps failed activation honest (API refusal %s)", async (api) => {
    mocks.post.mockRejectedValue(
      api
        ? new ApiError(409, { code: "NOT_READY", message: "raw details" })
        : new Error("connection"),
    );
    expect(await activateAssignmentAction(ASSIGNMENT_ID)).toEqual({
      error: api ? "That didn't work. Please try again." : "Could not reach the server.",
    });
    expect(mocks.revalidatePath).not.toHaveBeenCalled();
  });
  it.each([{ error: {} }, {}])(
    "does not show candidates after an incomplete recommendation response",
    async (response) => {
      mocks.get.mockResolvedValue(response);
      expect(
        await listAssignmentRecommendationsAction({
          campaign_id: ASSIGNMENT_ID,
          service_city: "Abuja",
        }),
      ).toEqual({ error: "Could not load drivers and cars." });
      expect(mocks.post).not.toHaveBeenCalled();
    },
  );
  it.each([true, false])(
    "reports failed recommendations without raw data (API %s)",
    async (api) => {
      mocks.get.mockRejectedValue(
        api
          ? new ApiError(403, { code: "FORBIDDEN", message: "raw driver data" })
          : new Error("connection"),
      );
      expect(
        await listAssignmentRecommendationsAction({
          campaign_id: ASSIGNMENT_ID,
          service_city: "Abuja",
        }),
      ).toEqual({
        error: api ? "That didn't work. Please try again." : "Could not reach the server.",
      });
      expect(mocks.post).not.toHaveBeenCalled();
    },
  );
});
