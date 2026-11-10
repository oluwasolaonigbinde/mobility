import "server-only";
import type { ApiClient } from "@/lib/api/client";
import { loadAdvertiserPageData } from "./page-data";
import { nigeriaDay } from "@/lib/campaigns/day-progress";
export type PerformanceDay = {
  date: string;
  distance_m: string | null;
  estimated_impressions: string | null;
  suppressed: boolean;
};
type Campaign = { start_at: string | null; end_at: string | null; status: string };
const DAY = 86400000;
const valid = (v: unknown): v is string =>
  typeof v === "string" && /^\d+(\.\d+)?$/.test(v) && Number.isFinite(Number(v));
const sum = (days: PerformanceDay[], field: "estimated_impressions" | "distance_m") =>
  days.reduce((n, d) => n + Number(d[field]), 0);
export function performanceWindow(c: Campaign, now: Date) {
  const today = Number.isFinite(now.getTime()) ? nigeriaDay(now.toISOString()) : null;
  const first = c.start_at ? nigeriaDay(c.start_at) : null;
  const end = c.end_at ? nigeriaDay(c.end_at) : null;
  if (
    today === null ||
    first === null ||
    (c.end_at && end === null) ||
    (end !== null && end < first)
  )
    return null;
  const last = Math.min(today - DAY, end ?? today - DAY);
  return { first, last, start: last - 13 * DAY };
}
export function summarizePerformance(c: Campaign, rows: PerformanceDay[] | null, now = new Date()) {
  const window = performanceWindow(c, now);
  const empty = c.status !== "cancelled" && (!window || window.last < window.first);
  const released =
    window && rows
      ? rows.filter((d) => {
          const day = nigeriaDay(d.date);
          return day !== null && day >= window.first && day >= window.start && day <= window.last;
        })
      : [];
  const latestStart = window ? window.last - 6 * DAY : 0;
  const latest = released.filter((d) => nigeriaDay(d.date)! >= latestStart);
  const expected = window
    ? Math.min(7, Math.floor((window.last - Math.max(window.first, latestStart)) / DAY) + 1)
    : 0;
  const dailyReady =
    !empty &&
    latest.length === expected &&
    latest.every(
      (d) => d.suppressed === false && valid(d.estimated_impressions) && valid(d.distance_m),
    );
  const fallback = c.status === "cancelled" || !dailyReady;
  const prior = released.filter((d) => nigeriaDay(d.date)! < latestStart);
  const comparison =
    !fallback &&
    window &&
    window.first <= window.start &&
    prior.length === 7 &&
    prior.every(
      (d) => d.suppressed === false && valid(d.estimated_impressions) && valid(d.distance_m),
    );
  const percent = (field: "estimated_impressions" | "distance_m") =>
    comparison && sum(prior, field) > 0
      ? ((sum(latest, field) - sum(prior, field)) / sum(prior, field)) * 100
      : null;
  const suppressed = latest.some((d) => d.suppressed);
  return {
    estimatedViews: fallback || empty ? null : String(sum(latest, "estimated_impressions")),
    distance: fallback || empty ? null : String(sum(latest, "distance_m")),
    viewChange: percent("estimated_impressions"),
    distanceChange: percent("distance_m"),
    priorViews:
      comparison && sum(prior, "estimated_impressions") > 0
        ? sum(prior, "estimated_impressions")
        : null,
    days: fallback || empty ? null : latest,
    windowLabel: empty
      ? "No results yet"
      : c.status === "cancelled"
        ? "Cancelled"
        : c.status === "finished"
          ? "Final 7 days"
          : "Last 7 days",
    dailyMessage: empty
      ? "No results yet"
      : c.status === "cancelled"
        ? null
        : suppressed
          ? "Not enough cars yet to show daily figures."
          : "Daily figures aren't ready yet.",
    fallback,
    unavailable: !rows && !empty && c.status !== "cancelled",
  };
}
export async function loadPerformance(
  api: ApiClient,
  campaignId: string,
  campaign: Campaign,
  now = new Date(),
) {
  const window = performanceWindow(campaign, now);
  const daily =
    window && window.last >= window.first && campaign.status !== "cancelled"
      ? await loadAdvertiserPageData(() =>
          api.GET("/api/v1/advertiser/campaigns/{campaign_id}/daily-metrics", {
            params: {
              path: { campaign_id: campaignId },
              query: {
                start_at: new Date(window.start - 3600000).toISOString(),
                end_at: new Date(window.last + DAY - 3600000).toISOString(),
                limit: 14,
              },
            },
          }),
        )
      : null;
  const rows =
    daily?.available &&
    daily.data.campaign_id === campaignId &&
    daily.data.total === 14 &&
    Array.isArray(daily.data.items) &&
    daily.data.items.length === 14 &&
    daily.data.items.every(
      (d, i) => d.date === new Date(window!.start + i * DAY).toISOString().slice(0, 10),
    )
      ? daily.data.items
      : null;
  return summarizePerformance(campaign, rows, now);
}
