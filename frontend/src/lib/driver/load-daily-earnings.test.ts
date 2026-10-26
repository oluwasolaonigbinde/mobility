import { describe, expect, it, vi } from "vitest";
import { ApiError } from "@/lib/api/errors";
import { loadDailyEarnings } from "./load-daily-earnings";
import type { ApiClient } from "@/lib/api/client";

function client(response: () => Promise<unknown>) {
  const get = vi.fn(response);
  return { api: { GET: get } as unknown as ApiClient, get };
}
const totals = [
  { currency: "NGN", today: "0.00", this_week: "5.00", total: "9.00", on_hold: "0.00" },
];

describe("daily earnings loading", () => {
  it("reads every day and the totals in one request", async () => {
    const { api, get } = client(async () => ({
      data: {
        totals,
        days: [
          {
            day: "2026-10-10",
            currency: "NGN",
            amount: "5.00",
            status: "paying_tonight",
            paid_at: null,
            trip_ids: [],
          },
        ],
      },
    }));
    expect(await loadDailyEarnings(api)).toEqual({
      state: "ready",
      data: {
        totals,
        days: [
          {
            day: "2026-10-10",
            currency: "NGN",
            amount: "5.00",
            status: "Paying tonight",
            paidAt: null,
            tripIds: [],
          },
        ],
      },
    });
    expect(get).toHaveBeenCalledTimes(1);
    expect(get).toHaveBeenCalledWith("/api/v1/driver/earnings/days");
  });
  it("withholds every figure when the history cannot be verified", async () => {
    const { api } = client(async () => {
      throw new ApiError(409, { code: "EARNINGS_DAYS_UNAVAILABLE", message: "x" });
    });
    expect(await loadDailyEarnings(api)).toEqual({ state: "unavailable" });
  });
  it("sends an expired session to sign in", async () => {
    const { api } = client(async () => {
      throw new ApiError(401, { code: "UNAUTHORIZED", message: "x" });
    });
    expect(await loadDailyEarnings(api)).toEqual({ state: "auth" });
  });
});
