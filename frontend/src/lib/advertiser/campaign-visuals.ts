import "server-only";
import type { ApiClient } from "@/lib/api/client";
import { loadAdvertiserPageData } from "./page-data";

export async function loadCampaignAreas(api: ApiClient, campaignId: string) {
  const first = await loadAdvertiserPageData(() =>
    api.GET("/api/v1/advertiser/campaigns/{campaign_id}/zones", {
      params: {
        path: { campaign_id: campaignId },
        query: { zone_type: "target", limit: 100, offset: 0 },
      },
    }),
  );
  if (!first.available) return first;
  const items = [...first.data.items];
  while (items.length < first.data.total) {
    const page = await loadAdvertiserPageData(() =>
      api.GET("/api/v1/advertiser/campaigns/{campaign_id}/zones", {
        params: {
          path: { campaign_id: campaignId },
          query: { zone_type: "target", limit: 100, offset: items.length },
        },
      }),
    );
    if (!page.available) return page;
    if (
      !page.data.items.length ||
      page.data.total !== first.data.total ||
      page.data.items.some((next) => items.some((item) => item.id === next.id))
    )
      return { available: false as const, reason: "protocol" as const };
    items.push(...page.data.items);
  }
  return { available: true as const, data: { ...first.data, items } };
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
