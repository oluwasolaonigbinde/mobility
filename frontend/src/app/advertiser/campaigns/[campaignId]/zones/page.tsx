import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { createApiClient } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import { getSessionToken } from "@/lib/auth/session";
import { statusLabel, statusTone } from "@/lib/campaigns/status";
import { StatusChip } from "@/components/ui/status-chip";
import { ZonesEditor } from "./zones-editor";

export const metadata: Metadata = { title: "Zones" };

export default async function CampaignZonesPage({
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
        / <span className="text-muted">Zones</span>
      </nav>

      <div className="mb-6 flex flex-wrap items-center gap-3">
        <h1 className="font-display text-3xl font-semibold tracking-tight">Targeting zones</h1>
        <StatusChip tone={statusTone[campaign.status]}>{statusLabel[campaign.status]}</StatusChip>
      </div>
      <p className="text-muted mb-6 max-w-2xl text-sm">
        Draw where campaign vehicle activity is prioritized. Target zones carry premium driver
        time, bonus zones add driver incentive, and exclusion zones are never billed.
      </p>

      <ZonesEditor campaignId={campaign.id} zones={zones?.items ?? []} />
    </div>
  );
}
