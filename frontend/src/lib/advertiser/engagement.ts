import "server-only";
import type { ApiClient } from "@/lib/api/client";
import { loadAdvertiserPageData } from "./page-data";

export async function loadLivePositions(api: ApiClient, campaignId: string) {
  const result = await loadAdvertiserPageData(() =>
    api.GET("/api/v1/advertiser/campaigns/{campaign_id}/live-positions", {
      params: { path: { campaign_id: campaignId } },
    }),
  );
  if (!result.available) return result;
  if (
    result.data.campaign_id !== campaignId ||
    result.data.delay_minutes !== 15 ||
    !Array.isArray(result.data.positions) ||
    result.data.positions.some(
      (point) =>
        !point ||
        typeof point !== "object" ||
        !Number.isFinite(point.longitude) ||
        !Number.isFinite(point.latitude) ||
        Math.abs(point.longitude) > 180 ||
        Math.abs(point.latitude) > 90,
    )
  ) {
    return { available: false as const, reason: "protocol" as const };
  }
  return {
    available: true as const,
    data: {
      campaign_id: result.data.campaign_id,
      delay_minutes: result.data.delay_minutes,
      positions: result.data.positions.map(({ longitude, latitude }) => ({ longitude, latitude })),
    },
  };
}

export function loadQRScans(api: ApiClient, campaignId: string) {
  return loadAdvertiserPageData(() =>
    api.GET("/api/v1/advertiser/campaigns/{campaign_id}/qr-scans", {
      params: { path: { campaign_id: campaignId } },
    }),
  );
}
