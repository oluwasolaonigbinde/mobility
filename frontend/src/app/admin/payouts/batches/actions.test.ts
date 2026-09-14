import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "@/lib/api/errors";

const mocks = vi.hoisted(() => ({ batchApi: vi.fn(), revalidatePath: vi.fn() }));
vi.mock("./batch-api", () => ({ batchApi: mocks.batchApi }));
vi.mock("next/cache", () => ({ revalidatePath: mocks.revalidatePath }));

import {
  allocateDebtAction,
  batchTransitionAction,
  createAndReserveBatchAction,
  pollLineAction,
  previewSelectionAction,
} from "./actions";

describe("payout batch actions", () => {
  beforeEach(() => vi.clearAllMocks());

  it("returns only the server selection total and does not mutate a draft during preview", async () => {
    mocks.batchApi.mockResolvedValueOnce({ currency: "NGN", total_amount: "125.10" });
    const ids = ["22222222-2222-4222-8222-222222222222"];
    expect(await previewSelectionAction("NGN", ids)).toEqual({
      currency: "NGN",
      total_amount: "125.10",
    });
    expect(mocks.batchApi).toHaveBeenCalledExactlyOnceWith("/selection-preview", {
      method: "POST",
      body: JSON.stringify({ currency: "NGN", ledger_entry_ids: ids }),
    });
    expect(mocks.revalidatePath).not.toHaveBeenCalled();
  });

  it("retains the durable reference when the create response is lost and redacts internal errors", async () => {
    mocks.batchApi.mockRejectedValueOnce(
      new Error("https://provider.invalid/private?token=secret"),
    );
    const data = new FormData();
    data.set("request_id", "11111111-1111-4111-8111-111111111111");
    data.set("currency", "NGN");
    data.set("ledger_entry_ids", "22222222-2222-4222-8222-222222222222");
    const result = await createAndReserveBatchAction({}, data);
    expect(result.batchId).toBe("11111111-1111-4111-8111-111111111111");
    expect(result.error).toMatch(/saved request/);
    expect(JSON.stringify(result)).not.toMatch(/provider.invalid|secret/);
  });

  it("never calls a queued submission paid or submitted", async () => {
    mocks.batchApi.mockResolvedValueOnce({ status: "reserved" });
    const data = new FormData();
    data.set("batch_id", "11111111-1111-4111-8111-111111111111");
    data.set("intent", "submit");
    const result = await batchTransitionAction({}, data);
    expect(result.done).toMatch(/^Submission queued/);
    expect(result.done).toMatch(/does not confirm submission or payment/);
  });

  it("creates a draft then reserves the exact ledger entries", async () => {
    mocks.batchApi
      .mockResolvedValueOnce({ id: "11111111-1111-4111-8111-111111111111" })
      .mockResolvedValueOnce({ status: "reserved" });
    const form = new FormData();
    form.set("request_id", "11111111-1111-4111-8111-111111111111");
    form.set("currency", "ngn");
    form.set(
      "ledger_entry_ids",
      "22222222-2222-4222-8222-222222222222, 33333333-3333-4333-8333-333333333333",
    );
    const result = await createAndReserveBatchAction({}, form);
    expect(result.done).toMatch(/reservation confirmed/i);
    expect(mocks.batchApi).toHaveBeenNthCalledWith(1, "", {
      method: "POST",
      body: JSON.stringify({ currency: "NGN", request_id: "11111111-1111-4111-8111-111111111111" }),
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

  it("does not call an old void batch a new reservation when recovering its exact request", async () => {
    mocks.batchApi
      .mockResolvedValueOnce({ id: "11111111-1111-4111-8111-111111111111" })
      .mockResolvedValueOnce({ status: "void" });
    const form = new FormData();
    form.set("request_id", "11111111-1111-4111-8111-111111111111");
    form.set("currency", "NGN");
    form.set("ledger_entry_ids", "22222222-2222-4222-8222-222222222222");
    const result = await createAndReserveBatchAction({}, form);
    expect(result.done).toMatch(/Existing batch recovered; no new reservation/);
    expect(result.done).not.toMatch(/Reservation confirmed/);
  });

  it("surfaces provider submission failure without claiming completion", async () => {
    mocks.batchApi.mockRejectedValueOnce(
      new ApiError(503, {
        code: "DISBURSEMENT_PROVIDER_UNAVAILABLE",
        message: "Automated submission is not configured",
      }),
    );
    const form = new FormData();
    form.set("batch_id", "11111111-1111-4111-8111-111111111111");
    form.set("intent", "submit");
    const result = await batchTransitionAction({}, form);
    expect(result.error).toMatch(/not configured.*No transfer is confirmed/);
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

  it("returns the immutable replacement for terminal failure without claiming same-key retry", async () => {
    mocks.batchApi.mockResolvedValueOnce({
      id: "44444444-4444-4444-8444-444444444444",
      status: "reserved",
    });
    const form = new FormData();
    form.set("batch_id", "11111111-1111-4111-8111-111111111111");
    form.set("intent", "retry_failed");
    const result = await batchTransitionAction({}, form);
    expect(result.done).toMatch(/replacement.*independent approval/i);
    expect(result.done).not.toMatch(/same.key|frozen idempotency/i);
    expect(result.batchId).toBe("44444444-4444-4444-8444-444444444444");
    expect(mocks.batchApi).toHaveBeenCalledWith(
      "/11111111-1111-4111-8111-111111111111/retry-failed",
      { method: "POST" },
    );
  });

  it("explains why an unchanged terminally failed destination cannot be retried", async () => {
    mocks.batchApi.mockRejectedValueOnce(
      new ApiError(409, {
        code: "PAYOUT_RESOLVED_LINES_NOT_RETRYABLE",
        message: "private backend detail",
      }),
    );
    const form = new FormData();
    form.set("batch_id", "11111111-1111-4111-8111-111111111111");
    form.set("intent", "retry_failed");
    expect((await batchTransitionAction({}, form)).error).toMatch(/newer verified bank/);
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

  it("allocates debt for one driver and currency before batching", async () => {
    mocks.batchApi.mockResolvedValueOnce({ settlement_ids: [] });
    const form = new FormData();
    form.set("driver_profile_id", "22222222-2222-4222-8222-222222222222");
    form.set("currency", "ngn");
    const result = await allocateDebtAction({}, form);
    expect(result.done).toMatch(/carry-forward debt/i);
    expect(mocks.batchApi).toHaveBeenCalledWith(
      "/debt-balances/22222222-2222-4222-8222-222222222222/allocate",
      { method: "POST", body: JSON.stringify({ currency: "NGN" }) },
    );
  });
});
