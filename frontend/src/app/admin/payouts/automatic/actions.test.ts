import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "@/lib/api/errors";

const mocks = vi.hoisted(() => ({ post: vi.fn(), revalidatePath: vi.fn() }));
vi.mock("@/lib/api/client", () => ({ createApiClient: () => ({ POST: mocks.post }) }));
vi.mock("@/lib/auth/session", () => ({ getSessionToken: vi.fn(async () => "token") }));
vi.mock("next/cache", () => ({ revalidatePath: mocks.revalidatePath }));

import { releaseUnsentAction, resolveAlertAction, switchAutomaticPayoutsAction } from "./actions";

const ALERT_ID = "7f9c1f4e-8a5b-4c3d-9e2f-1a2b3c4d5e6f";

function form(values: Record<string, string>): FormData {
  const data = new FormData();
  for (const [key, value] of Object.entries(values)) data.set(key, value);
  return data;
}

describe("automatic payout actions", () => {
  beforeEach(() => vi.clearAllMocks());

  it("pauses and resumes with the trimmed reason", async () => {
    mocks.post.mockResolvedValue({ data: {} });
    expect(
      await switchAutomaticPayoutsAction({}, form({ intent: "pause", reason: "  Bank check  " })),
    ).toEqual({ done: "Automatic payouts are paused." });
    expect(mocks.post).toHaveBeenLastCalledWith("/api/v1/admin/payouts/automatic/pause", {
      body: { reason: "Bank check" },
    });
    expect(
      await switchAutomaticPayoutsAction({}, form({ intent: "resume", reason: "All clear" })),
    ).toEqual({ done: "Automatic payouts are running again." });
    expect(mocks.post).toHaveBeenLastCalledWith("/api/v1/admin/payouts/automatic/resume", {
      body: { reason: "All clear" },
    });
    expect(mocks.revalidatePath).toHaveBeenCalledWith("/admin/payouts/automatic");
  });

  it("refuses a short reason before calling the API and shows server errors", async () => {
    expect(await switchAutomaticPayoutsAction({}, form({ intent: "pause", reason: "x" }))).toEqual({
      error: "Give a reason of at least 3 characters — it is kept in the audit trail",
    });
    expect(mocks.post).not.toHaveBeenCalled();
    mocks.post.mockRejectedValueOnce(
      new ApiError(409, {
        code: "PAYOUT_AUTOMATIC_ALREADY_PAUSED",
        message: "Automatic payouts are already paused",
      }),
    );
    expect(
      await switchAutomaticPayoutsAction({}, form({ intent: "pause", reason: "Again" })),
    ).toEqual({ error: "Automatic payouts are already paused" });
    mocks.post.mockRejectedValueOnce(new Error("offline"));
    expect(await releaseUnsentAction({}, form({ reason: "Move them" }))).toEqual({
      error: "Could not reach the server. Try again.",
    });
  });

  it("reports how many unsent payments moved", async () => {
    mocks.post.mockResolvedValueOnce({ data: { released_count: 2, released_amount: "10.00" } });
    expect(await releaseUnsentAction({}, form({ reason: "Month end" }))).toEqual({
      done: "2 unsent payments moved to manual review.",
    });
    mocks.post.mockResolvedValueOnce({ data: { released_count: 1, released_amount: "5.00" } });
    expect(await releaseUnsentAction({}, form({ reason: "Month end" }))).toEqual({
      done: "1 unsent payment moved to manual review.",
    });
    mocks.post.mockResolvedValueOnce({ data: { released_count: 0, released_amount: "0.00" } });
    expect(await releaseUnsentAction({}, form({ reason: "Month end" }))).toEqual({
      done: "There were no unsent automatic payments to move.",
    });
    expect(await releaseUnsentAction({}, form({ reason: "" }))).toHaveProperty("error");
  });

  it("resolves an alert by id with a note", async () => {
    mocks.post.mockResolvedValueOnce({ data: {} });
    expect(
      await resolveAlertAction({}, form({ alert_id: ALERT_ID, note: "Called the driver" })),
    ).toEqual({ done: "Marked as followed up." });
    expect(mocks.post).toHaveBeenCalledWith(
      "/api/v1/admin/payouts/automatic/alerts/{alert_id}/resolve",
      { params: { path: { alert_id: ALERT_ID } }, body: { note: "Called the driver" } },
    );
    expect(await resolveAlertAction({}, form({ alert_id: "nope", note: "Fine" }))).toHaveProperty(
      "error",
    );
    mocks.post.mockRejectedValueOnce(
      new ApiError(409, {
        code: "PAYOUT_AUTOMATIC_ALERT_RESOLVED",
        message: "This alert is already followed up",
      }),
    );
    expect(await resolveAlertAction({}, form({ alert_id: ALERT_ID, note: "Again" }))).toEqual({
      error: "This alert is already followed up",
    });
  });
});
