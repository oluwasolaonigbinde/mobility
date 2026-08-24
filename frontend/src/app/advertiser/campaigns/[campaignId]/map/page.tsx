import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { createApiClient } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import { getSessionToken } from "@/lib/auth/session";
import { statusLabel, statusTone } from "@/lib/campaigns/status";
import { StatusChip } from "@/components/ui/status-chip";
import { HeatmapView } from "./heatmap-view";

export const metadata: Metadata = { title: "Live map" };

export default async function CampaignMapPage({
  params,
}: {
  params: Promise<{ campaignId: string }>;
}) {
  const { campaignId } = await params;
  const api = createApiClient(await getSessionToken());

  let campaign, zones;
  try {
    [{ data: campaign }, { data: zones }] = await Promise.all([
      api.GET("/api/v1/advertiser/campaigns/{campaign_id}", {
        params: { path: { campaign_id: campaignId } },
      }),
      api.GET("/api/v1/advertiser/campaigns/{campaign_id}/zones", {
        params: { path: { campaign_id: campaignId }, query: { limit: 100 } },
      }),
    ]);
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) notFound();
    throw error;
  }
  if (!campaign) notFound();

  return (
    <div className="animate-rise mx-auto max-w-6xl">
      <nav aria-label="Breadcrumb" className="micro text-faint mb-4">
        <Link href="/advertiser/campaigns" className="hover:text-muted">
          Campaigns
        </Link>{" "}
        /{" "}
        <Link href={`/advertiser/campaigns/${campaign.id}`} className="hover:text-muted">
          {campaign.name}
        </Link>{" "}
        / <span className="text-muted">Exposure map</span>
      </nav>

      <p className="micro text-amber mb-2">Exposure heatmap</p>
      <div className="mb-2 flex flex-wrap items-center gap-3">
        <h1 className="font-display text-3xl font-semibold tracking-tight">
          Where your campaign was seen
        </h1>
        <StatusChip tone={statusTone[campaign.status]}>{statusLabel[campaign.status]}</StatusChip>
      </div>
      <p className="text-muted mb-6 max-w-2xl text-sm">
        Compare estimated impressions and verified vehicle movement across the areas your campaign
        reached.
      </p>

      <HeatmapView campaignId={campaign.id} zones={zones?.items ?? []} />
    </div>
  );
}
