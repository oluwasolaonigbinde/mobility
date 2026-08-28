import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "@/lib/api/errors";

const mocks = vi.hoisted(() => ({
  post: vi.fn(),
  revalidatePath: vi.fn(),
}));

vi.mock("next/cache", () => ({ revalidatePath: mocks.revalidatePath }));
vi.mock("@/lib/auth/session", () => ({ getSessionToken: vi.fn(async () => "token") }));
vi.mock("@/lib/api/client", () => ({ createApiClient: () => ({ POST: mocks.post }) }));

import { submitFraudDisputeAction } from "./actions";

const FLAG_ID = "00000000-0000-4000-8000-00000000000a";
const TRIP_ID = "00000000-0000-4000-8000-00000000000b";

function disputeForm(message: string): FormData {
  const form = new FormData();
  form.set("flag_id", FLAG_ID);
  form.set("trip_id", TRIP_ID);
  form.set("message", message);
  return form;
}

describe("submitFraudDisputeAction", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.post.mockResolvedValue({ data: {} });
  });

  it("normalizes the message and submits through the owner-scoped endpoint", async () => {
    await expect(
      submitFraudDisputeAction({}, disputeForm("  GPS paused near the bridge.  ")),
    ).resolves.toEqual({
      done: "Your dispute was submitted for staff review.",
    });
    expect(mocks.post).toHaveBeenCalledWith("/api/v1/driver/fraud-holds/{flag_id}/disputes", {
      params: { path: { flag_id: FLAG_ID } },
      body: { message: "GPS paused near the bridge." },
    });
    expect(mocks.revalidatePath).toHaveBeenCalledWith(`/driver/earnings/trips/${TRIP_ID}`);
  });

  it("rejects a blank message without a backend call", async () => {
    await expect(submitFraudDisputeAction({}, disputeForm("   "))).resolves.toEqual({
      error: "Tell us what you would like reviewed",
    });
    expect(mocks.post).not.toHaveBeenCalled();
  });

  it("turns the one-dispute conflict into safe refresh guidance", async () => {
    mocks.post.mockRejectedValue(
      new ApiError(409, { code: "CONFLICT", message: "internal conflict detail" }),
    );

    await expect(submitFraudDisputeAction({}, disputeForm("Please review."))).resolves.toEqual({
      error: "A dispute already exists for this assessment. Refresh to see it.",
    });
    expect(mocks.revalidatePath).not.toHaveBeenCalled();
  });

  it.each([401, 403])("does not retry a revoked or unauthorized session (%s)", async (status) => {
    mocks.post.mockRejectedValue(
      new ApiError(status, { code: "SESSION_REJECTED", message: "private auth detail" }),
    );

    await expect(submitFraudDisputeAction({}, disputeForm("Please review."))).resolves.toEqual({
      error: "Your session is no longer valid. Sign in again before retrying.",
    });
    expect(mocks.post).toHaveBeenCalledOnce();
    expect(mocks.revalidatePath).not.toHaveBeenCalled();
  });
});
