import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  post: vi.fn(),
  revalidatePath: vi.fn(),
}));

vi.mock("next/cache", () => ({ revalidatePath: mocks.revalidatePath }));
vi.mock("@/lib/auth/session", () => ({ getSessionToken: vi.fn(async () => "token") }));
vi.mock("@/lib/api/client", () => ({
  createApiClient: () => ({ POST: mocks.post }),
}));

import { recordSpotCheckAction, replyFraudDisputeAction, reviewFraudFlagAction } from "./actions";

const FLAG_ID = "00000000-0000-4000-8000-00000000000a";
const DISPUTE_ID = "00000000-0000-4000-8000-00000000000b";

function reviewForm(intent: string, note?: string): FormData {
  const form = new FormData();
  form.set("flag_id", FLAG_ID);
  form.set("intent", intent);
  if (note !== undefined) form.set("note", note);
  return form;
}

describe("reviewFraudFlagAction", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.post.mockResolvedValue({ data: {} });
  });

  it("refuses the removed acknowledge step without changing a flag", async () => {
    expect(await reviewFraudFlagAction({}, reviewForm("acknowledge"))).toHaveProperty("error");
    expect(mocks.post).not.toHaveBeenCalled();
    expect(mocks.revalidatePath).not.toHaveBeenCalled();
  });

  it("trims the mandatory resolution note before sending it", async () => {
    await reviewFraudFlagAction({}, reviewForm("dismiss", "  Duplicate test route.  "));

    expect(mocks.post).toHaveBeenCalledWith("/api/v1/admin/fraud-flags/{flag_id}/review/resolve", {
      params: { path: { flag_id: FLAG_ID } },
      body: { outcome: "dismissed", note: "Duplicate test route." },
    });
  });

  it("rejects a blank note without calling the backend", async () => {
    await expect(reviewFraudFlagAction({}, reviewForm("confirm", "   "))).resolves.toEqual({
      error: "A review note is required",
    });
    expect(mocks.post).not.toHaveBeenCalled();
    expect(mocks.revalidatePath).not.toHaveBeenCalled();
  });
});

describe("replyFraudDisputeAction", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.post.mockResolvedValue({ data: {} });
  });

  it("trims the driver-facing reply and uses the dedicated endpoint", async () => {
    const form = new FormData();
    form.set("dispute_id", DISPUTE_ID);
    form.set("reply", "  We reviewed the route and cleared the hold.  ");

    await expect(replyFraudDisputeAction({}, form)).resolves.toEqual({
      done: "Reply sent to driver",
    });
    expect(mocks.post).toHaveBeenCalledWith("/api/v1/admin/fraud-disputes/{dispute_id}/reply", {
      params: { path: { dispute_id: DISPUTE_ID } },
      body: { reply: "We reviewed the route and cleared the hold." },
    });
    expect(mocks.revalidatePath).toHaveBeenCalledWith("/admin/trip-checks");
  });

  it("rejects a blank reply without touching the backend", async () => {
    const form = new FormData();
    form.set("dispute_id", DISPUTE_ID);
    form.set("reply", "   ");

    await expect(replyFraudDisputeAction({}, form)).resolves.toEqual({
      error: "A driver reply is required",
    });
    expect(mocks.post).not.toHaveBeenCalled();
  });
});

describe("physical spot-check actions", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.post.mockResolvedValue({ data: {} });
  });

  it.each([
    ["passed", "In-person check passed"],
    ["failed", "Failure sent to trip review"],
  ])("records %s with the inspector note and stable request id", async (outcome, done) => {
    const form = new FormData();
    form.set("assignment_id", "00000000-0000-4000-8000-000000000001");
    form.set("trip_session_id", "00000000-0000-4000-8000-000000000002");
    form.set("client_request_id", "00000000-0000-4000-8000-000000000003");
    form.set("outcome", outcome);
    form.set("note", "  In-person observation.  ");
    await expect(recordSpotCheckAction({}, form)).resolves.toEqual({ done });
    expect(mocks.post).toHaveBeenCalledWith(
      "/api/v1/admin/evidence-verifications/physical-spot-checks",
      {
        body: {
          assignment_id: "00000000-0000-4000-8000-000000000001",
          trip_session_id: "00000000-0000-4000-8000-000000000002",
          client_request_id: "00000000-0000-4000-8000-000000000003",
          outcome,
          note: "In-person observation.",
        },
      },
    );
  });
});
