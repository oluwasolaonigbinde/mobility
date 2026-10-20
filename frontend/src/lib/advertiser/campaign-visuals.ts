import "server-only";
import type { ApiClient } from "@/lib/api/client";
import { loadAdvertiserPageData, loadAllAdvertiserPages } from "./page-data";

/** Every zone of one campaign (target areas only unless `allTypes`), or why they are unavailable. */
export async function loadCampaignAreas(api: ApiClient, campaignId: string, allTypes = false) {
  const zoneType = allTypes ? undefined : ("target" as const);
  const areas = await loadAllAdvertiserPages(
    (offset) =>
      api.GET("/api/v1/advertiser/campaigns/{campaign_id}/zones", {
        params: {
          path: { campaign_id: campaignId },
          query: { zone_type: zoneType, limit: 100, offset },
        },
      }),
    (item) => item.campaign_id === campaignId,
  );
  return areas.available
    ? { available: true as const, data: { items: areas.data, total: areas.data.length } }
    : areas;
}

export async function loadCampaignVisuals(api: ApiClient, campaignId: string) {
  const [artwork, areas] = await Promise.all([
    loadAdvertiserPageData(() =>
      api.GET("/api/v1/advertiser/campaigns/{campaign_id}/creatives", {
        params: { path: { campaign_id: campaignId }, query: { limit: 100, offset: 0 } },
      }),
    ),
    loadCampaignAreas(api, campaignId),
  ]);
  return { artwork, areas };
}

export function previewFile(
  items: Array<{
    stored_file_id: string | null;
    creative_type: string;
    asset_source: string;
    scan_status: string | null;
    status: string;
  }>,
) {
  const eligible = items.filter(
    (item) =>
      item.creative_type === "image" &&
      item.asset_source === "managed_file" &&
      item.scan_status === "clean" &&
      item.status !== "archived",
  );
  return (eligible.find((item) => item.status === "approved") ?? eligible[0])?.stored_file_id;
}
