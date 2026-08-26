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

import {
  queueSpotCheckAction,
  replyFraudDisputeAction,
  resolveSpotCheckAction,
  reviewFraudFlagAction,
} from "./actions";

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

  it("acknowledges through the typed review endpoint and revalidates the queue", async () => {
    await expect(reviewFraudFlagAction({}, reviewForm("acknowledge"))).resolves.toEqual({
      done: "Review acknowledged",
    });
    expect(mocks.post).toHaveBeenCalledWith(
      "/api/v1/admin/fraud-flags/{flag_id}/review/acknowledge",
      { params: { path: { flag_id: FLAG_ID } } },
    );
    expect(mocks.revalidatePath).toHaveBeenCalledWith("/admin/fraud");
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
    expect(mocks.revalidatePath).toHaveBeenCalledWith("/admin/fraud");
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

  it("queues one assignment-bound physical check", async () => {
    const form = new FormData();
    form.set("assignment_id", "00000000-0000-4000-8000-000000000001");
    form.set("trip_session_id", "00000000-0000-4000-8000-000000000002");
    form.set("note", "  Inspect the display in person.  ");

    await expect(queueSpotCheckAction({}, form)).resolves.toEqual({
      done: "Physical spot check queued",
    });
    expect(mocks.post).toHaveBeenCalledWith(
      "/api/v1/admin/evidence-verifications/physical-spot-checks",
      {
        body: expect.objectContaining({
          assignment_id: "00000000-0000-4000-8000-000000000001",
          trip_session_id: "00000000-0000-4000-8000-000000000002",
          note: "Inspect the display in person.",
          client_request_id: expect.any(String),
        }),
      },
    );
  });

  it("records a failed result through the hold-producing endpoint", async () => {
    const form = new FormData();
    form.set("verification_id", "00000000-0000-4000-8000-000000000003");
    form.set("outcome", "failed");
    form.set("note", "  Display was not present.  ");

    await expect(resolveSpotCheckAction({}, form)).resolves.toEqual({
      done: "Failure sent to fraud review",
    });
    expect(mocks.post).toHaveBeenCalledWith(
      "/api/v1/admin/evidence-verifications/{verification_id}/physical-spot-check-result",
      expect.objectContaining({
        params: {
          path: { verification_id: "00000000-0000-4000-8000-000000000003" },
        },
        body: expect.objectContaining({ outcome: "failed", note: "Display was not present." }),
      }),
    );
  });
});
