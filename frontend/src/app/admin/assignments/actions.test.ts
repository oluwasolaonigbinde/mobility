import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  post: vi.fn(),
  get: vi.fn(),
  redirect: vi.fn(),
  revalidatePath: vi.fn(),
}));

vi.mock("next/cache", () => ({ revalidatePath: mocks.revalidatePath }));
vi.mock("@/lib/auth/session", () => ({ getSessionToken: vi.fn(async () => "token") }));
vi.mock("@/lib/api/client", () => ({
  createApiClient: () => ({ POST: mocks.post, GET: mocks.get }),
}));

vi.mock("next/navigation", async (importOriginal) => ({
  ...(await importOriginal<typeof import("next/navigation")>()),
  redirect: mocks.redirect,
}));

import { ApiError } from "@/lib/api/errors";
import {
  activateAssignmentAction,
  cancelAssignmentAction,
  createAssignmentAction,
  listAssignmentRecommendationsAction,
} from "./actions";

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

describe("createAssignmentAction", () => {
  const id = "00000000-0000-4000-8000-000000000001";

  function offer(expiry = "2026-11-19T00:00") {
    const data = new FormData();
    for (const field of ["campaign_id", "driver_profile_id", "vehicle_id", "creative_id"]) {
      data.set(field, id);
    }
    data.set("expires_at", expiry);
    data.set("recommendation_service_city", "Lagos");
    data.set("recommendation_vehicle_type", "car");
    data.set("recommendation_matching_version", "matching_v1");
    data.set("recommendation_fingerprint", "a".repeat(64));
    return data;
  }

  beforeEach(() => {
    mocks.post.mockReset();
    vi.spyOn(Date, "now").mockReturnValue(Date.parse("2026-11-18T22:30:00Z"));
  });
  afterEach(() => vi.restoreAllMocks());

  it("sends the chosen recommendation and converts midnight WAT to the prior UTC date", async () => {
    await createAssignmentAction({}, offer());
    expect(mocks.post).toHaveBeenCalledWith("/api/v1/admin/campaign-assignments", {
      body: {
        campaign_id: id,
        driver_profile_id: id,
        vehicle_id: id,
        creative_id: id,
        expires_at: "2026-11-18T23:00:00.000Z",
        notes: null,
        recommendation_context: {
          service_city: "Lagos",
          vehicle_type: "car",
          matching_version: "matching_v1",
          fingerprint: "a".repeat(64),
        },
      },
    });
    expect(mocks.redirect).toHaveBeenCalledWith(`/admin/campaigns/${id}#drivers`);
  });

  it("checks the future boundary after converting from Nigeria time", async () => {
    expect(await createAssignmentAction({}, offer("2026-11-18T23:30"))).toEqual({
      error: "Choose a valid offer expiry in the future.",
    });
    expect(mocks.post).not.toHaveBeenCalled();
  });

  it("returns plain copy for incomplete recommendation evidence", async () => {
    const form = offer();
    form.delete("recommendation_vehicle_type");
    expect(await createAssignmentAction({}, form)).toEqual({
      error: "Find drivers again and choose a current recommendation.",
    });
    expect(mocks.post).not.toHaveBeenCalled();
  });

  it("asks for an expiry when none was chosen", async () => {
    const form = offer();
    form.delete("expires_at");
    expect(await createAssignmentAction({}, form)).toEqual({
      error: "Choose a valid offer expiry in the future.",
    });
    expect(mocks.post).not.toHaveBeenCalled();
  });

  it("sends a manual offer without recommendation context", async () => {
    const form = offer();
    for (const field of [
      "recommendation_service_city",
      "recommendation_vehicle_type",
      "recommendation_matching_version",
      "recommendation_fingerprint",
    ])
      form.delete(field);
    form.set("notes", "  Park near the gate  ");
    await createAssignmentAction({}, form);
    expect(mocks.post).toHaveBeenCalledWith("/api/v1/admin/campaign-assignments", {
      body: expect.not.objectContaining({ recommendation_context: expect.anything() }),
    });
    expect(mocks.post.mock.calls[0]?.[1].body.notes).toBe("Park near the gate");
  });

  it("asks for shorter notes when they exceed 500 characters", async () => {
    const form = offer();
    form.set("notes", "x".repeat(501));
    expect(await createAssignmentAction({}, form)).toEqual({
      error: "Keep your notes to 500 characters or fewer.",
    });
    expect(mocks.post).not.toHaveBeenCalled();
  });

  it("asks for every offer choice when one is missing", async () => {
    const form = offer();
    form.delete("vehicle_id");
    expect(await createAssignmentAction({}, form)).toEqual({
      error: "Choose a campaign, driver, car and approved artwork.",
    });
    expect(mocks.post).not.toHaveBeenCalled();
  });

  it("reports an unreachable server without redirecting", async () => {
    mocks.redirect.mockClear();
    mocks.post.mockRejectedValueOnce(new TypeError("fetch failed"));
    expect(await createAssignmentAction({}, offer())).toEqual({
      error: "Could not reach the server.",
    });
    expect(mocks.redirect).not.toHaveBeenCalled();
  });

  it.each([
    ["FROZEN_PAYOUT_TERMS_REQUIRED", "Set pay terms that are in effect before offering jobs."],
    ["STALE_RECOMMENDATION", "Find drivers again and choose a current recommendation."],
    [
      "DRIVER_PERSON_PAYEE_NOT_APPROVED",
      "Approve the driver’s identity and payment details first.",
    ],
    ["UNRECOGNISED_CODE", "That didn't work. Please try again."],
  ])("shows fixed copy for %s", async (code, error) => {
    mocks.post.mockRejectedValueOnce(new ApiError(409, { code, message: "Internal detail" }));
    expect(await createAssignmentAction({}, offer())).toEqual({ error });
  });

  it("keeps the driver-city recovery action", async () => {
    mocks.post.mockRejectedValueOnce(
      new ApiError(409, {
        code: "DRIVER_SERVICE_AREA_REQUIRED",
        message: "Internal detail",
      }),
    );
    expect(await createAssignmentAction({}, offer())).toEqual({
      cityRequiredForDriver: id,
      error: "Add the driver’s city before sending a job offer.",
    });
  });
});
