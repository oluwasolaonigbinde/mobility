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

import { reviewFraudFlagAction } from "./actions";

const FLAG_ID = "00000000-0000-4000-8000-00000000000a";

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
