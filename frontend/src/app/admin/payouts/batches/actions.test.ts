import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({ batchApi: vi.fn(), revalidatePath: vi.fn() }));
vi.mock("./batch-api", () => ({ batchApi: mocks.batchApi }));
vi.mock("next/cache", () => ({ revalidatePath: mocks.revalidatePath }));

import { batchTransitionAction, createAndReserveBatchAction, pollLineAction } from "./actions";

describe("payout batch actions", () => {
  beforeEach(() => vi.clearAllMocks());

  it("creates a draft then reserves the exact ledger entries", async () => {
    mocks.batchApi
      .mockResolvedValueOnce({ id: "11111111-1111-4111-8111-111111111111" })
      .mockResolvedValueOnce({ status: "reserved" });
    const form = new FormData();
    form.set("currency", "ngn");
    form.set(
      "ledger_entry_ids",
      "22222222-2222-4222-8222-222222222222, 33333333-3333-4333-8333-333333333333",
    );
    const result = await createAndReserveBatchAction({}, form);
    expect(result.done).toMatch(/reserved/i);
    expect(mocks.batchApi).toHaveBeenNthCalledWith(1, "", {
      method: "POST",
      body: JSON.stringify({ currency: "NGN" }),
    });
    expect(mocks.batchApi).toHaveBeenNthCalledWith(
      2,
      "/11111111-1111-4111-8111-111111111111/reserve",
      {
        method: "POST",
        body: JSON.stringify({
          ledger_entry_ids: [
            "22222222-2222-4222-8222-222222222222",
            "33333333-3333-4333-8333-333333333333",
          ],
        }),
      },
    );
  });

  it("surfaces provider submission failure without claiming completion", async () => {
    mocks.batchApi.mockRejectedValueOnce(new Error("Automated submission is not configured"));
    const form = new FormData();
    form.set("batch_id", "11111111-1111-4111-8111-111111111111");
    form.set("intent", "submit");
    const result = await batchTransitionAction({}, form);
    expect(result).toEqual({ error: "Automated submission is not configured" });
    expect(mocks.revalidatePath).not.toHaveBeenCalled();
  });

  it("rejects malformed ledger IDs before any API mutation", async () => {
    const form = new FormData();
    form.set("currency", "NGN");
    form.set("ledger_entry_ids", "not-a-uuid");
    const result = await createAndReserveBatchAction({}, form);
    expect(result.error).toMatch(/valid ledger entry/i);
    expect(mocks.batchApi).not.toHaveBeenCalled();
  });

  it("retries failed lines through the bounded batch endpoint", async () => {
    mocks.batchApi.mockResolvedValueOnce({ status: "submitted" });
    const form = new FormData();
    form.set("batch_id", "11111111-1111-4111-8111-111111111111");
    form.set("intent", "retry_failed");
    const result = await batchTransitionAction({}, form);
    expect(result.done).toMatch(/idempotency/i);
    expect(mocks.batchApi).toHaveBeenCalledWith(
      "/11111111-1111-4111-8111-111111111111/retry-failed",
      { method: "POST" },
    );
  });

  it("polls only the selected provider line", async () => {
    mocks.batchApi.mockResolvedValueOnce({ status: "completed" });
    const form = new FormData();
    form.set("line_id", "22222222-2222-4222-8222-222222222222");
    const result = await pollLineAction({}, form);
    expect(result.done).toMatch(/provider result/i);
    expect(mocks.batchApi).toHaveBeenCalledWith(
      "/lines/22222222-2222-4222-8222-222222222222/poll",
      { method: "POST" },
    );
  });
});
