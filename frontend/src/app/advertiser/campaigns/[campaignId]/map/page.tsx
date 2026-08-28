import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { createApiClient } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import { getSessionToken } from "@/lib/auth/session";
import { statusLabel, statusTone } from "@/lib/campaigns/status";
import { StatusChip } from "@/components/ui/status-chip";
import { HighExposureZoneInsights } from "@/components/analytics/high-exposure-zone-insights";
import {
  GovernedAnalysisState,
  validateMeasurementAuthority,
} from "../report/measurement-authority";
import { GovernedZoneMap, type GovernedZoneGeometry } from "./heatmap-view";

export const metadata: Metadata = { title: "Governed coverage map" };

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
    return (
      <GovernedAnalysisState
        code={error instanceof ApiError ? error.code : "MAP_SOURCE_UNAVAILABLE"}
      />
    );
  }
  if (!campaign) notFound();

  let report;
  try {
    ({ data: report } = await api.GET("/api/v1/advertiser/campaigns/{campaign_id}/report", {
      params: { path: { campaign_id: campaignId } },
    }));
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) notFound();
    return (
      <GovernedAnalysisState
        code={error instanceof ApiError ? error.code : "MAP_SOURCE_UNAVAILABLE"}
      />
    );
  }
  if (!report) return <GovernedAnalysisState code="SAFE_MEASUREMENT_RUN_REQUIRED" />;
  const authority = validateMeasurementAuthority(report);
  if (!authority.ok) return <GovernedAnalysisState code="MEASUREMENT_RUN_INTEGRITY_FAILURE" />;

  const zoneInsights = report.high_exposure_zone_insights;
  if (!zoneInsights) return <GovernedAnalysisState code="ZONE_PROJECTION_UNAVAILABLE" />;
  if (zoneInsights.state === "ready" && zoneInsights.items.length === 0) {
    return <GovernedAnalysisState code="ZONE_PROJECTION_INTEGRITY_FAILURE" />;
  }
  const targetZones = new Map(
    (zones?.items ?? [])
      .filter((zone) => zone.zone_type === "target")
      .map((zone) => [zone.id, zone] as const),
  );
  const governedZones: GovernedZoneGeometry[] = [];
  if (zoneInsights.state === "ready") {
    for (const item of zoneInsights.items) {
      const zone = targetZones.get(item.zone_id);
      if (zone?.name === item.zone_name) {
        governedZones.push({ rank: item.rank, name: zone.name, geometry: zone.geometry });
      }
    }
  }
  if (zoneInsights.state === "ready" && governedZones.length !== zoneInsights.items.length) {
    return <GovernedAnalysisState code="ZONE_PROJECTION_INTEGRITY_FAILURE" />;
  }

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
        / <span className="text-muted">Campaign coverage map</span>
      </nav>

      <p className="micro text-amber mb-2">Campaign coverage map</p>
      <div className="mb-2 flex flex-wrap items-center gap-3">
        <h1 className="font-display text-3xl font-semibold tracking-tight">
          Where campaign vehicles moved
        </h1>
        <StatusChip tone={statusTone[campaign.status]}>{statusLabel[campaign.status]}</StatusChip>
      </div>
      <p className="text-muted mb-6 max-w-2xl text-sm">
        View only disclosure-cleared target zones ranked by the same frozen measurement run used for
        Campaign Performance Analysis.
      </p>

      <div className="flex flex-col gap-4">
        <HighExposureZoneInsights insight={zoneInsights} surface="map" />
        {zoneInsights.state === "ready" ? <GovernedZoneMap zones={governedZones} /> : null}
      </div>
    </div>
  );
}
