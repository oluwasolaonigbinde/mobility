import { render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
const { get, guard } = vi.hoisted(() => ({ get: vi.fn(), guard: vi.fn() }));
vi.mock("@/lib/api/client", () => ({ createApiClient: () => ({ GET: get }) }));
vi.mock("@/lib/auth/session", () => ({ getSessionToken: async () => "token" }));
vi.mock("@/lib/auth/current-user", () => ({ requireRole: guard }));
vi.mock("next/headers", () => ({
  headers: async () => new Headers({ "x-cardvert-admin-path": "/admin" }),
}));
import Page from "./page";
import { collectWorkQueue, waitingCounts } from "./work-queue";
import type { ApiClient } from "@/lib/api/client";
const date = "2026-09-01T00:00:00Z";
const api = { GET: get } as unknown as ApiClient;
const page = (query: Record<string, string> = {}) => Page({ searchParams: Promise.resolve(query) });
describe("Bounded Work queue", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    guard.mockResolvedValue({});
    get.mockResolvedValue({ data: { items: [], total: 0 } });
  });
  it("requests only oldest five with full counts and no later-page download", async () => {
    get.mockImplementation(async (path, options) =>
      path.endsWith("/driver-applications")
        ? {
            data: {
              items: Array.from({ length: options.params.query.limit }, (_, i) => ({
                id: `app${i}`,
                driver_profile_id: `driver${i}`,
                full_name: `Driver ${i}`,
                created_at: date,
              })),
              total: 101,
            },
          }
        : { data: { items: [], total: 0 } },
    );
    render(await page());
    const region = screen.getByRole("region", { name: "Operations" });
    expect(within(region).getAllByRole("listitem")).toHaveLength(5);
    expect(within(region).getByRole("link", { name: "See all (101)" })).toBeVisible();
    const reads = get.mock.calls.filter(([p]) => p.endsWith("/driver-applications"));
    expect(reads).toHaveLength(1);
    expect(reads[0]![1].params.query).toMatchObject({ limit: 5, offset: 0, oldest_first: true });
  });
  it("count-only badge mode requests one row and retains the full filtered total", async () => {
    get.mockImplementation(async (path) =>
      path.endsWith("/driver-applications")
        ? {
            data: {
              items: [
                { id: "app", driver_profile_id: "driver", full_name: "Ada", created_at: date },
              ],
              total: 120,
            },
          }
        : { data: { items: [], total: 0 } },
    );
    const queue = await collectWorkQueue(api, 1);
    expect(waitingCounts(queue).drivers).toBe(120);
    expect(get.mock.calls.every(([, o]) => o.params.query.limit === 1)).toBe(true);
    expect(get).toHaveBeenCalledTimes(17);
  });
  it("asks the server for actionable contact/change/run rows before totals", async () => {
    await collectWorkQueue(api);
    expect(
      get.mock.calls.find(([p]) => p.endsWith("/manual-driver-contact-tasks"))?.[1].params.query,
    ).toMatchObject({ open_only: true, history: false });
    expect(
      get.mock.calls.find(([p]) => p.endsWith("/campaign-change-requests/pending"))?.[1].params
        .query.status,
    ).toBe("pending_admin");
    expect(
      get.mock.calls.find(([p]) => p.endsWith("/payout-batches/summaries"))?.[1].params.query
        .needs_attention,
    ).toBe(true);
  });
  it("shows one grouped trip with its actual held money once", async () => {
    get.mockImplementation(async (path) =>
      path.endsWith("/fraud-flags")
        ? {
            data: {
              items: [
                {
                  id: "flag",
                  trip_session_id: "trip",
                  driver_name: "Ada",
                  trip_started_at: date,
                  detected_at: date,
                  problem_count: 2,
                  money_effect: { held_pending_net: "3263.51", held_currency: "NGN" },
                },
              ],
              total: 1,
            },
          }
        : { data: { items: [], total: 0 } },
    );
    const queue = await collectWorkQueue(api);
    const row = await queue.Operations![0]!.describe();
    expect(row.reason).toMatch(/2 problems.*3,263.51 held/);
    expect(waitingCounts(queue).trips).toBe(1);
    expect(
      get.mock.calls.find(([p]) => p.endsWith("/fraud-flags"))?.[1].params.query,
    ).toMatchObject({ group_by_trip: true, unresolved_only: true });
  });
  it("retains failure instead of inventing an empty list or zero badge", async () => {
    get.mockImplementation(async (path) => {
      if (path.endsWith("/vehicles")) throw new Error("offline");
      return { data: { items: [], total: 0 } };
    });
    const queue = await collectWorkQueue(api);
    expect(waitingCounts(queue).drivers).toBeUndefined();
    render(await page());
    expect(
      within(screen.getByRole("region", { name: "Operations" })).getByRole("alert"),
    ).toBeVisible();
    expect(
      within(screen.getByRole("region", { name: "Finance" })).getByText("Nothing waiting"),
    ).toBeVisible();
  });
});
