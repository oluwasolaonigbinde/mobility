import "server-only";
import type { ApiClient } from "@/lib/api/client";
import { readCampaignPerformance } from "@/lib/api/audit-batch2";
import { loadAdvertiserPageData } from "./page-data";
import { loadQRScans } from "./engagement";

export async function loadPerformance(api: ApiClient, campaignId: string, now = new Date()) {
  const today = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Africa/Lagos",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(now);
  const dates = Array.from({ length: 7 }, (_, index) =>
    new Date(Date.parse(`${today}T12:00:00Z`) - (6 - index) * 86_400_000)
      .toISOString()
      .slice(0, 10),
  );
  const [performance, daily, scans] = await Promise.all([
    loadAdvertiserPageData(() => readCampaignPerformance(api, campaignId)),
    loadAdvertiserPageData(() =>
      api.GET("/api/v1/advertiser/campaigns/{campaign_id}/daily-metrics", {
        params: {
          path: { campaign_id: campaignId },
        },
      }),
    ),
    loadQRScans(api, campaignId),
  ]);
  const validPerformance =
    performance.available &&
    performance.data.campaign_id === campaignId &&
    Boolean(performance.data.totals) &&
    (performance.data.totals.estimated_views === null ||
      (typeof performance.data.totals.estimated_views === "string" &&
        /^\d+(\.\d+)?$/.test(performance.data.totals.estimated_views)));
  const validDaily =
    daily.available &&
    daily.data.campaign_id === campaignId &&
    Array.isArray(daily.data.items) &&
    daily.data.total === daily.data.items.length &&
    daily.data.items.length === 7 &&
    daily.data.items.every(
      (item, index) =>
        item.date === dates[index] &&
        typeof item.suppressed === "boolean" &&
        (item.suppressed
          ? item.distance_m === null
          : typeof item.distance_m === "string" && /^\d+(\.\d+)?$/.test(item.distance_m)),
    );
  const validScans =
    scans.available &&
    scans.data.campaign_id === campaignId &&
    Number.isSafeInteger(scans.data.scans) &&
    scans.data.scans >= 0;
  return {
    estimatedViews: validPerformance ? performance.data.totals.estimated_views : null,
    period: validPerformance
      ? { start_at: performance.data.start_at, end_at: performance.data.end_at }
      : undefined,
    days: validDaily
      ? daily.data.items.map(({ date, distance_m }) => ({ date, distance_m }))
      : null,
    scans: validScans ? scans.data.scans : null,
    withheld: validPerformance
      ? performance.data.totals.estimated_views === null
      : !performance.available && performance.reason === "insufficient",
    daysWithheld: validDaily
      ? daily.data.items.some((item) => item.suppressed)
      : !daily.available && daily.reason === "insufficient",
    unavailable:
      (!validPerformance && (performance.available || performance.reason !== "insufficient")) ||
      (!validDaily && (daily.available || daily.reason !== "insufficient")) ||
      !validScans,
  };
}
