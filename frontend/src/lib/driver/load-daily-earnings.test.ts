import { describe, expect, it, vi } from "vitest";
import { loadDailyEarnings } from "./load-daily-earnings";
import type { ApiClient } from "@/lib/api/client";

const row = (id: number) => ({
  id: String(id),
  amount: "1.00",
  currency: "NGN",
  work_days: [{ day: "2026-10-10", amount: "1.00" }],
  status: "available",
  entry_type: "trip_payout",
});
function client(pages: unknown[]) {
  const get = vi.fn(async (path: string) =>
    path.endsWith("fraud-holds") ? { data: { items: [] } } : pages.shift(),
  );
  return { api: { GET: get } as unknown as ApiClient, get };
}
describe("complete daily ledger loading", () => {
  it("joins a day split across two pages", async () => {
    const { api, get } = client([
      { data: { items: Array.from({ length: 100 }, (_, id) => row(id)), total: 101 } },
      { data: { items: [row(100)], total: 101 } },
    ]);
    expect(await loadDailyEarnings(api)).toMatchObject({
      state: "ready",
      data: [{ amount: "101.00" }],
    });
    expect(get.mock.calls.at(-1)?.[0]).toBe("/api/v1/driver/earnings/ledger");
  });
  it("withholds day totals when the later page fails", async () => {
    const { api } = client([
      { data: { items: Array.from({ length: 100 }, (_, id) => row(id)), total: 101 } },
      {},
    ]);
    expect(await loadDailyEarnings(api)).toEqual({ state: "unavailable" });
  });
  it("withholds totals when a later correction changes history size", async () => {
    const { api } = client([
      { data: { items: Array.from({ length: 100 }, (_, id) => row(id)), total: 101 } },
      { data: { items: [row(100)], total: 102 } },
    ]);
    expect(await loadDailyEarnings(api)).toEqual({ state: "unavailable" });
  });
  it("does not treat missing allocations as an empty ledger", async () => {
    const { api } = client([{ data: { items: [{ ...row(0), work_days: [] }], total: 1 } }]);
    expect(await loadDailyEarnings(api)).toEqual({ state: "unavailable" });
  });
  it("accepts an authoritative empty history", async () => {
    const { api } = client([{ data: { items: [], total: 0 } }]);
    expect(await loadDailyEarnings(api)).toEqual({ state: "ready", data: [] });
  });
});
