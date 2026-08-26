import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { createApiClient } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import { getSessionToken } from "@/lib/auth/session";
import {
  formatCount,
  formatDate,
  formatDateRange,
  formatKm,
  formatMoney,
  formatScore,
} from "@/lib/format";
import { statusLabel, statusTone } from "@/lib/campaigns/status";
import { Panel } from "@/components/ui/panel";
import { Stat } from "@/components/ui/stat";
import { StatusChip } from "@/components/ui/status-chip";
import { StatusActions } from "./status-actions";
import { CommercialPanel } from "./commercial-panel";
import { CreativeStatusActions } from "./creative-status-actions";

export const metadata: Metadata = { title: "Campaign" };

const creativeTypeLabel: Record<string, string> = {
  image: "Image",
  video: "Video",
  html: "HTML",
  text: "Text",
  other: "Other",
};

const placementLabel: Record<string, string> = {
  vehicle_exterior: "Vehicle exterior",
  vehicle_interior: "Vehicle interior",
  digital_screen: "Digital screen",
  print: "Print",
  other: "Other",
};

export default async function CampaignDetailPage({
  params,
  searchParams,
}: {
  params: Promise<{ campaignId: string }>;
  searchParams: Promise<{ commercial_error?: string }>;
}) {
  const { campaignId } = await params;
  const query = await searchParams;
  const api = createApiClient(await getSessionToken());

  let campaign, summary, creatives, commercial, reviewHistory;
  try {
    [
      { data: campaign },
      { data: summary },
      { data: creatives },
      { data: commercial },
      { data: reviewHistory },
    ] = await Promise.all([
      api.GET("/api/v1/advertiser/campaigns/{campaign_id}", {
        params: { path: { campaign_id: campaignId } },
      }),
      api.GET("/api/v1/advertiser/campaigns/{campaign_id}/summary", {
        params: { path: { campaign_id: campaignId } },
      }),
      api.GET("/api/v1/advertiser/campaigns/{campaign_id}/creatives", {
        params: { path: { campaign_id: campaignId } },
      }),
      api.GET("/api/v1/advertiser/campaigns/{campaign_id}/commercial", {
        params: { path: { campaign_id: campaignId } },
      }),
      api.GET("/api/v1/advertiser/campaigns/{campaign_id}/review-history", {
        params: { path: { campaign_id: campaignId } },
      }),
    ]);
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) notFound();
    throw error;
  }
  if (!campaign) notFound();

  const cost = summary?.costs.totals_by_currency[0];
  const creativeItems = creatives?.items ?? [];

  return (
    <div className="animate-rise mx-auto max-w-6xl">
      <nav aria-label="Breadcrumb" className="micro text-faint mb-4">
        <Link href="/advertiser/campaigns" className="hover:text-muted">
          Campaigns
        </Link>{" "}
        / <span className="text-muted">{campaign.name}</span>
      </nav>

      <div className="mb-8 flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="font-display text-3xl font-semibold tracking-tight">{campaign.name}</h1>
            <StatusChip tone={statusTone[campaign.status]}>
              {statusLabel[campaign.status]}
            </StatusChip>
          </div>
          <p className="micro text-muted mt-1.5">
            {formatDateRange(campaign.start_at, campaign.end_at)} · created{" "}
            {formatDate(campaign.created_at)}
          </p>
        </div>
        <div className="flex flex-col items-end gap-2">
          <StatusActions campaignId={campaign.id} status={campaign.status} />
          <div className="flex flex-wrap justify-end gap-2">
            <Link
              href={`/advertiser/campaigns/${campaign.id}/report`}
              className="micro border-edge bg-raised hover:border-edge-strong rounded-lg border px-3.5 py-2.5 transition-colors"
            >
              📊 Report
            </Link>
            <Link
              href={`/advertiser/campaigns/${campaign.id}/map`}
              className="micro border-edge bg-raised hover:border-edge-strong rounded-lg border px-3.5 py-2.5 transition-colors"
            >
              🔥 Coverage map
            </Link>
            <Link
              href={`/advertiser/campaigns/${campaign.id}/zones`}
              className="micro border-edge bg-raised hover:border-edge-strong rounded-lg border px-3.5 py-2.5 transition-colors"
            >
              🗺 Zones · {formatCount(summary?.zones.total)}
            </Link>
          </div>
        </div>
      </div>

      {/* Performance */}
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-3 xl:grid-cols-6">
        <Stat
          label="Modelled potential contacts"
          value={formatCount(summary?.impressions.estimated_impressions)}
          hint={`${formatCount(summary?.impressions.estimated_trip_count)} estimated trips`}
        />
        <Stat
          label="Model confidence diagnostic"
          value={formatScore(summary?.impressions.average_confidence_score)}
          hint="Formula diagnostic, not a statistical confidence interval"
          tone="cyan"
        />
        <Stat
          label="Distance covered"
          value={formatKm(summary?.route_analytics.total_distance_m)}
          hint={`${formatKm(summary?.route_analytics.target_zone_distance_m)} in target zones`}
        />
        <Stat
          label="Quality score"
          value={formatScore(summary?.route_analytics.average_quality_score)}
          tone="amber"
        />
        <Stat
          label="Driver campaign cost"
          value={cost ? formatMoney(cost.final_payout_total, cost.currency) : "—"}
          tone="green"
          hint="Verified driver payout projection — not advertiser spend"
        />
        <Stat
          label="Fraud flags"
          value={formatCount(summary?.fraud_flags.open)}
          tone={(summary?.fraud_flags.open ?? 0) > 0 ? "coral" : "green"}
          hint="Open on this campaign"
        />
      </div>

      {commercial ? (
        <CommercialPanel
          campaignId={campaign.id}
          commercial={commercial}
          error={query.commercial_error}
        />
      ) : null}

      <Panel className="mt-6 overflow-hidden" aria-label="Review history">
        <div className="border-edge border-b px-6 py-4">
          <h2 className="micro text-muted">Review history</h2>
          <p className="text-faint mt-1 text-xs">
            Immutable server-recorded submission and decision history.
          </p>
        </div>
        {(reviewHistory?.items ?? []).length === 0 ? (
          <p className="text-muted px-6 py-6 text-sm">
            This campaign has not been submitted for review.
          </p>
        ) : (
          <ol className="divide-edge/60 divide-y">
            {(reviewHistory?.items ?? []).map((event) => (
              <li key={event.id} className="px-6 py-4">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="flex items-center gap-2">
                    <StatusChip tone={statusTone[event.new_status]}>
                      {statusLabel[event.new_status]}
                    </StatusChip>
                    <p className="text-sm">
                      {event.prior_status === "rejected" && event.new_status === "pending_review"
                        ? "Resubmitted for review"
                        : `${statusLabel[event.prior_status]} → ${statusLabel[event.new_status]}`}
                    </p>
                  </div>
                  <p className="micro text-faint">{formatDate(event.created_at)}</p>
                </div>
                {event.rejection_reason ? (
                  <p className="text-coral mt-2 text-sm">Reason: {event.rejection_reason}</p>
                ) : null}
                {event.reviewed_snapshot_sha256 ? (
                  <p className="micro text-faint mt-2 font-mono break-all">
                    Submitted snapshot SHA-256: {event.reviewed_snapshot_sha256}
                  </p>
                ) : null}
              </li>
            ))}
          </ol>
        )}
      </Panel>

      <div className="mt-6 grid gap-6 lg:grid-cols-3">
        {/* Details */}
        <Panel className="p-6 lg:col-span-1">
          <h2 className="micro text-muted mb-4">Campaign details</h2>
          <dl className="flex flex-col gap-3 text-sm">
            {campaign.description ? (
              <div>
                <dt className="micro text-faint">Description</dt>
                <dd className="mt-1">{campaign.description}</dd>
              </div>
            ) : null}
            <div>
              <dt className="micro text-faint">Window</dt>
              <dd className="mt-1 font-mono text-xs">
                {formatDateRange(campaign.start_at, campaign.end_at)}
              </dd>
            </div>
            <div>
              <dt className="micro text-faint">Total budget</dt>
              <dd className="mt-1 font-mono text-xs">
                {formatMoney(campaign.budget_amount, campaign.currency)}
              </dd>
            </div>
            <div>
              <dt className="micro text-faint">Daily budget</dt>
              <dd className="mt-1 font-mono text-xs">
                {formatMoney(campaign.daily_budget_amount, campaign.currency)}
              </dd>
            </div>
            <div>
              <dt className="micro text-faint">Fleet</dt>
              <dd className="mt-1 font-mono text-xs">
                {formatCount(summary?.assignments.active)} active ·{" "}
                {formatCount(summary?.assignments.total)} assigned vehicles
              </dd>
            </div>
          </dl>
        </Panel>

        {/* Creatives */}
        <Panel className="overflow-hidden lg:col-span-2">
          <div className="border-edge flex items-center justify-between border-b px-6 py-4">
            <h2 className="micro text-muted">Creatives · {creativeItems.length}</h2>
          </div>
          {creativeItems.length === 0 ? (
            <p className="text-muted px-6 py-10 text-center text-sm">
              No creatives yet. Upload a private creative file when you edit this campaign.
            </p>
          ) : (
            <ul className="divide-edge/60 divide-y">
              {creativeItems.map((cr) => (
                <li key={cr.id} className="flex items-center justify-between gap-4 px-6 py-4">
                  <div className="min-w-0">
                    <p className="truncate text-sm font-medium">{cr.name}</p>
                    <p className="micro text-faint mt-0.5">
                      {creativeTypeLabel[cr.creative_type] ?? cr.creative_type} ·{" "}
                      {placementLabel[cr.placement] ?? cr.placement}
                      {cr.width_px && cr.height_px ? ` · ${cr.width_px}×${cr.height_px}` : ""}
                      {cr.asset_source === "managed_file"
                        ? ` · security scan: ${cr.scan_status ?? "unavailable"}`
                        : " · legacy URL (not launch-authoritative)"}
                    </p>
                  </div>
                  <div className="flex shrink-0 flex-col items-end gap-2">
                    <StatusChip
                      tone={
                        cr.status === "approved"
                          ? "green"
                          : cr.status === "rejected"
                            ? "coral"
                            : cr.status === "archived" || cr.status === "ready"
                              ? "default"
                              : "amber"
                      }
                    >
                      {cr.status.replace("_", " ")}
                    </StatusChip>
                    <CreativeStatusActions
                      campaignId={campaign.id}
                      creativeId={cr.id}
                      status={cr.status}
                    />
                  </div>
                </li>
              ))}
            </ul>
          )}
        </Panel>
      </div>
    </div>
  );
}
