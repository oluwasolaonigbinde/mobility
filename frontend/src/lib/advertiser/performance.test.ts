import { expect, it, vi } from "vitest";
import type { ApiClient } from "@/lib/api/client";
import { loadPerformance } from "./performance";
const now = new Date("2026-10-20T23:30:00Z"); // Already 21 October in Nigeria.
const dates = [
  "2026-10-15",
  "2026-10-16",
  "2026-10-17",
  "2026-10-18",
  "2026-10-19",
  "2026-10-20",
  "2026-10-21",
];
function daily() {
  return {
    campaign_id: "one",
    total: 7,
    items: dates.map((date, index) => ({
      date,
      distance_m: index === 6 ? "25000" : "0",
      suppressed: false,
    })),
  };
}
function client(patch: Record<string, unknown> = {}) {
  const data: Record<string, unknown> = {
    "/report": {
      campaign_id: "one",
      totals: { estimated_views: "0" },
      start_at: null,
      end_at: null,
    },
    "/daily-metrics": daily(),
    "/qr-scans": { campaign_id: "one", scans: 0 },
    ...patch,
  };
  const get = vi.fn(async (path: string) => ({
    data: data[Object.keys(data).find((key) => path.endsWith(key))!],
  }));
  return { api: { GET: get } as unknown as ApiClient, get };
}
it("reads seven Nigeria days through partial today without overriding the server's WAT window", async () => {
  const { api, get } = client();
  const result = await loadPerformance(api, "one", now);
  expect(result).toMatchObject({
    estimatedViews: "0",
    scans: 0,
    unavailable: false,
    daysWithheld: false,
  });
  expect(result.days).toHaveLength(7);
  expect(result.days?.at(-1)).toEqual({ date: "2026-10-21", distance_m: "25000" });
  expect(result.days?.[0]).toEqual({ date: "2026-10-15", distance_m: "0" });
  expect(get).toHaveBeenCalledWith("/api/v1/advertiser/campaigns/{campaign_id}/daily-metrics", {
    params: { path: { campaign_id: "one" } },
  });
});
it("keeps suppressed days null and honest without presenting an operational error", async () => {
  const projection = daily();
  const items = projection.items.map((item, index) =>
    index === 1 ? { ...item, distance_m: null, suppressed: true } : item,
  );
  const { api } = client({
    "/daily-metrics": { ...projection, items },
    "/report": { campaign_id: "one", totals: { estimated_views: null } },
  });
  const result = await loadPerformance(api, "one", now);
  expect(result).toMatchObject({ daysWithheld: true, withheld: true, unavailable: false });
  expect(result.days?.[1]?.distance_m).toBeNull();
  expect(result.days?.[0]?.distance_m).toBe("0");
});
it("rejects another tenant, partial or malformed daily series without inventing zeros", async () => {
  for (const invalid of [
    { ...daily(), campaign_id: "other" },
    { ...daily(), items: daily().items.slice(1), total: 6 },
    { ...daily(), items: daily().items.map((item) => ({ ...item, date: dates[0] })) },
    { ...daily(), items: daily().items.map((item) => ({ ...item, distance_m: "broken" })) },
    { ...daily(), items: daily().items.map((item) => ({ ...item, suppressed: true })) },
  ]) {
    const { api } = client({ "/daily-metrics": invalid });
    expect(await loadPerformance(api, "one", now)).toMatchObject({ days: null, unavailable: true });
  }
});
