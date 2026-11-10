import { expect, it, vi } from "vitest";
import type { ApiClient } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import { loadPerformance, summarizePerformance, type PerformanceDay } from "./performance";
const now = new Date("2026-11-15T12:00Z");
const campaign = {
  start_at: "2026-11-01T00:00:00+01:00",
  end_at: "2026-12-01T00:00Z",
  status: "active",
};
const rows = (): PerformanceDay[] =>
  Array.from({ length: 14 }, (_, i) => ({
    date: `2026-11-${String(i + 1).padStart(2, "0")}`,
    distance_m: i < 7 ? "1000" : "2000",
    estimated_impressions: i < 7 ? "10" : "20",
    suppressed: false,
  }));
it("sums released latest seven (140 views, 14km) and compares prior 70 views, 7km", () => {
  expect(summarizePerformance(campaign, rows(), now)).toMatchObject({
    estimatedViews: "140",
    distance: "14000",
    viewChange: 100,
    distanceChange: 100,
    windowLabel: "Last 7 days",
  });
});
it.each([
  ["2026-11-13T00:00:00+01:00", "40", 2],
  ["2026-11-05T00:00:00+01:00", "140", 7],
])("clamps start %s without a prior comparison", (start_at, views, count) => {
  const result = summarizePerformance({ ...campaign, start_at }, rows(), now);
  expect(result.estimatedViews).toBe(views);
  expect(result.days).toHaveLength(count);
  expect(result.viewChange).toBeNull();
});
it.each([0, 13])("suppressed day %s never enters comparison", (index) => {
  const days = rows();
  days[index] = {
    ...days[index]!,
    suppressed: true,
    estimated_impressions: null,
    distance_m: null,
  };
  const result = summarizePerformance(campaign, days, now);
  expect(result.viewChange).toBeNull();
  expect(result.estimatedViews).toBe(index === 13 ? null : "140");
  if (index === 13) expect(result.dailyMessage).toBe("Not enough cars yet to show daily figures.");
});
it("null views fall back without inventing zeros", () => {
  const days = rows();
  days[13]!.estimated_impressions = null;
  expect(summarizePerformance(campaign, days, now)).toMatchObject({
    estimatedViews: null,
    windowLabel: "Last 7 days",
    days: null,
    viewChange: null,
    dailyMessage: "Daily figures aren't ready yet.",
  });
});
it("zero prior has no percent", () => {
  const days = rows();
  days.slice(0, 7).forEach((d) => (d.estimated_impressions = "0"));
  expect(summarizePerformance(campaign, days, now).viewChange).toBeNull();
});
it("before first complete day shows no results or zeros", () =>
  expect(
    summarizePerformance({ ...campaign, start_at: "2026-11-15T00:00:00+01:00" }, rows(), now),
  ).toMatchObject({ estimatedViews: null, days: null, windowLabel: "No results yet" }));
it("cancelled exposes no figures or chart", () =>
  expect(summarizePerformance({ ...campaign, status: "cancelled" }, rows(), now)).toMatchObject({
    estimatedViews: null,
    days: null,
    viewChange: null,
    windowLabel: "Cancelled",
  }));
it("finished window ends on campaign's last day", async () => {
  const get = vi.fn(async () => ({
    data: { campaign_id: "one", items: rows(), total: 14 },
  }));
  const result = await loadPerformance(
    { GET: get } as unknown as ApiClient,
    "one",
    { ...campaign, status: "finished", end_at: "2026-11-14T23:00:00+01:00" },
    now,
  );
  expect(result.windowLabel).toBe("Final 7 days");
  expect(get.mock.calls).toHaveLength(1);
  expect(get).toHaveBeenCalledWith(expect.stringContaining("daily-metrics"), {
    params: {
      path: { campaign_id: "one" },
      query: {
        start_at: "2026-10-31T23:00:00.000Z",
        end_at: "2026-11-14T23:00:00.000Z",
        limit: 14,
      },
    },
  });
});
it("null views in the prior window hides only the comparison", () => {
  const days = rows();
  days[0]!.estimated_impressions = null;
  expect(summarizePerformance(campaign, days, now)).toMatchObject({
    estimatedViews: "140",
    viewChange: null,
    windowLabel: "Last 7 days",
  });
});

it("cancelled before a complete day exposes no figures", () =>
  expect(
    summarizePerformance(
      { ...campaign, status: "cancelled", start_at: "2026-11-15T00:00:00+01:00" },
      rows(),
      now,
    ),
  ).toMatchObject({
    windowLabel: "Cancelled",
    estimatedViews: null,
    days: null,
    viewChange: null,
  }));
it("malformed daily data falls back without crashing the page", async () => {
  const get = vi.fn(async () => ({
    data: { campaign_id: "one", total: 14 },
  }));
  expect(
    await loadPerformance({ GET: get } as unknown as ApiClient, "one", campaign, now),
  ).toMatchObject({ estimatedViews: null, windowLabel: "Last 7 days", unavailable: true });
});

it.each(["cancelled", "active", "finished"])(
  "failed %s windows never fetch or expose whole totals",
  async (status) => {
    const get = vi.fn(async () => {
      throw new ApiError(503, { code: "DOWN", message: "daily unavailable" });
    });
    const result = await loadPerformance(
      { GET: get } as unknown as ApiClient,
      "one",
      { ...campaign, status },
      now,
    );
    expect(result).toMatchObject({
      fallback: true,
      estimatedViews: null,
      distance: null,
      days: null,
      viewChange: null,
      distanceChange: null,
    });
    expect(get.mock.calls).toHaveLength(status === "cancelled" ? 0 : 1);
    if (status !== "cancelled")
      expect(get).toHaveBeenCalledWith(
        expect.stringContaining("/daily-metrics"),
        expect.anything(),
      );
  },
);
