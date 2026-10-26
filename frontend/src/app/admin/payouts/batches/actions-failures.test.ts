import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "@/lib/api/errors";

const mocks = vi.hoisted(() => ({
  batchApi: vi.fn(),
  revalidatePath: vi.fn(),
  post: vi.fn(),
}));
vi.mock("./batch-api", () => ({ batchApi: mocks.batchApi }));
vi.mock("next/cache", () => ({ revalidatePath: mocks.revalidatePath }));
vi.mock("@/lib/api/client", () => ({ createApiClient: () => ({ POST: mocks.post }) }));
vi.mock("@/lib/auth/session", () => ({ getSessionToken: async () => "token" }));

import {
  maskedDestinationAction,
  negativeAdjustmentAction,
  pollLineAction,
  previewSelectionAction,
} from "./actions";

const version = "33333333-3333-4333-8333-333333333333";
const entry = "22222222-2222-4222-8222-222222222222";

describe("payout action failure paths", () => {
  beforeEach(() => vi.clearAllMocks());

  function adjustment(amount = "999999999999.99") {
    const form = new FormData();
    form.set("entry_id", entry);
    form.set("request_id", version);
    form.set("currency", "NGN");
    form.set("amount", amount);
    form.set("reason", "Correct recorded overpayment");
    form.set("lagos_day", "2026-10-20");
    return form;
  }

  it("preserves the exact decimal, reference and Nigeria day on an uncertain adjustment retry", async () => {
    mocks.post.mockRejectedValueOnce(new Error("lost response"));
    const form = adjustment();
    expect(await negativeAdjustmentAction({}, form)).toEqual({
      error: "No result was confirmed. Retry the same adjustment or check the ledger.",
    });
    expect(mocks.revalidatePath).not.toHaveBeenCalled();
    mocks.post.mockResolvedValueOnce({ data: { id: version } });
    expect(await negativeAdjustmentAction({}, form)).toEqual({
      done: "Negative adjustment recorded. Other trips' pay is unchanged.",
    });
    expect(mocks.post.mock.calls[0]).toEqual(mocks.post.mock.calls[1]);
    expect(mocks.post).toHaveBeenLastCalledWith(
      "/api/v1/admin/earnings-ledger/{entry_id}/negative-adjustments",
      {
        params: { path: { entry_id: entry } },
        body: {
          request_id: version,
          currency: "NGN",
          amount: "999999999999.99",
          reason: "Correct recorded overpayment",
          lagos_day: "2026-10-20",
        },
      },
    );
  });

  it.each(["0", "-1", "1.001", "1e3", "1000000000000"])(
    "refuses invalid adjustment amount %s before any mutation",
    async (amount) => {
      expect((await negativeAdjustmentAction({}, adjustment(amount))).error).toBeTruthy();
      expect(mocks.post).not.toHaveBeenCalled();
    },
  );

  it("refuses an invalid preview selection before calling the server", async () => {
    expect(await previewSelectionAction("ngn", [entry])).toEqual({
      error: "Select available credits in one currency.",
    });
    expect(await previewSelectionAction("NGN", [])).toEqual({
      error: "Select available credits in one currency.",
    });
    expect(await previewSelectionAction("NGN", ["not-a-uuid"])).toEqual({
      error: "Select available credits in one currency.",
    });
    expect(mocks.batchApi).not.toHaveBeenCalled();
  });

  it("maps a preview refusal to a public message and hides unexpected failures", async () => {
    mocks.batchApi.mockRejectedValueOnce(
      new ApiError(409, { code: "PAYOUT_ENTRY_HELD", message: "internal hold detail" }),
    );
    expect(await previewSelectionAction("NGN", [entry])).toEqual({
      error: "A selected credit is now held for review. Refresh available earnings.",
    });
    mocks.batchApi.mockRejectedValueOnce(new Error("socket hang up"));
    expect(await previewSelectionAction("NGN", [entry])).toEqual({
      error: "Selection could not be verified. Refresh available earnings.",
    });
  });

  it("keeps the current line authoritative when polling fails or input is invalid", async () => {
    const invalid = new FormData();
    invalid.set("line_id", "line");
    expect(await pollLineAction({}, invalid)).toEqual({ error: "Invalid selected payment" });

    mocks.batchApi.mockRejectedValueOnce(new Error("timeout"));
    const form = new FormData();
    form.set("reason", "Staff payment review");
    form.set("line_id", entry);
    expect(await pollLineAction({}, form)).toEqual({
      error:
        "No verified result could be confirmed. The current payment status remains authoritative.",
    });
    expect(mocks.revalidatePath).not.toHaveBeenCalled();
  });

  it("returns only a destination mask for an explicit audited review", async () => {
    mocks.post.mockResolvedValueOnce({
      data: { bank_code: "058", account_number: "0123456789", account_name: "Ada" },
    });
    const result = await maskedDestinationAction(version);
    expect(result).toEqual({ mask: "Bank 058 · account ending 6789" });
    expect(JSON.stringify(result)).not.toContain("0123456789");
    expect(JSON.stringify(result)).not.toContain("Ada");
    expect(mocks.post).toHaveBeenCalledWith(
      "/api/v1/admin/payees/bank-account-versions/{version_id}/reveal",
      {
        params: { path: { version_id: version } },
        body: { purpose: "payout_destination_review" },
      },
    );
  });

  it("refuses invalid, missing, forbidden and unavailable destination reviews", async () => {
    expect(await maskedDestinationAction("version")).toEqual({
      error: "Select a verified destination.",
    });
    expect(mocks.post).not.toHaveBeenCalled();

    mocks.post.mockResolvedValueOnce({ data: undefined });
    expect(await maskedDestinationAction(version)).toEqual({
      error: "Destination could not be verified.",
    });

    mocks.post.mockRejectedValueOnce(
      new ApiError(403, { code: "FORBIDDEN_ROLE", message: "forbidden" }),
    );
    expect(await maskedDestinationAction(version)).toEqual({
      error: "Administrator access is required.",
    });

    mocks.post.mockRejectedValueOnce(new ApiError(500, { code: "INTERNAL", message: "boom" }));
    expect(await maskedDestinationAction(version)).toEqual({
      error: "Destination details are unavailable. No payment has been authorized.",
    });
  });
});
