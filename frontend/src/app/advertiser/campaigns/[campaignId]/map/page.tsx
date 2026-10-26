import { notFound } from "next/navigation";
import { createApiClient } from "@/lib/api/client";
import { readCampaignPerformance } from "@/lib/api/audit-batch2";
import { getSessionToken } from "@/lib/auth/session";
import { loadAdvertiserPageData } from "@/lib/advertiser/page-data";
import { loadCampaignAreas } from "@/lib/advertiser/campaign-visuals";
import { AreaGraphic } from "@/components/campaigns/area-graphic";
import { DataUnavailable } from "@/components/ui/data-unavailable";
import { Panel } from "@/components/ui/panel";
import { PerformanceAreas } from "../report/performance-areas";

export const metadata = { title: "Campaign areas" };
export default async function CampaignMapPage({
  params,
}: {
  params: Promise<{ campaignId: string }>;
}) {
  const { campaignId } = await params;
  const api = createApiClient(await getSessionToken());
  const [areas, result] = await Promise.all([
    loadCampaignAreas(api, campaignId),
    loadAdvertiserPageData(() => readCampaignPerformance(api, campaignId)),
  ]);
  if (
    (!areas.available && areas.reason === "missing") ||
    (!result.available && result.reason === "missing")
  )
    notFound();
  if (result.available && result.data.campaign_id !== campaignId) notFound();
  return (
    <div className="mx-auto max-w-5xl">
      <h1 className="font-display text-3xl font-semibold">Your campaign areas</h1>
      <p className="text-muted mt-3 text-sm">The areas chosen for your campaign.</p>
      {areas.available ? (
        areas.data.items.length ? (
          <Panel className="mt-5 overflow-hidden">
            <div className="h-72">
              <AreaGraphic areas={areas.data.items} />
            </div>
          </Panel>
        ) : (
          <p className="text-muted mt-5 text-sm">No campaign areas have been chosen yet.</p>
        )
      ) : (
        <DataUnavailable
          title="Area picture unavailable"
          reason={areas.reason}
          retryHref={`/advertiser/campaigns/${campaignId}/map`}
        />
      )}
      {result.available ? (
        <>
          <PerformanceAreas areas={result.data.areas} />
          <p className="text-muted mt-4 text-sm">{result.data.completeness}</p>
          <p className="text-muted mt-2 text-sm">{result.data.uncertainty}</p>
        </>
      ) : (
        <DataUnavailable
          title="Area results unavailable"
          reason={result.reason}
          retryHref={`/advertiser/campaigns/${campaignId}/map`}
        />
      )}
    </div>
  );
}
