import { notFound } from "next/navigation";
import { createApiClient } from "@/lib/api/client";
import { readCampaignPerformance } from "@/lib/api/audit-batch2";
import { getSessionToken } from "@/lib/auth/session";
import { loadAdvertiserPageData } from "@/lib/advertiser/page-data";
import { formatCount, formatDateRange, formatKm } from "@/lib/format";
import { DataUnavailable } from "@/components/ui/data-unavailable";
import { Panel } from "@/components/ui/panel";
import { ReportIssuancePanel } from "./report-issuance-panel";
import { PerformanceAreas } from "./performance-areas";

export const metadata = { title: "Campaign results" };
export default async function CampaignReportPage({
  params,
}: {
  params: Promise<{ campaignId: string }>;
}) {
  const { campaignId } = await params;
  const api = createApiClient(await getSessionToken());
  const result = await loadAdvertiserPageData(() => readCampaignPerformance(api, campaignId));
  if (!result.available) {
    if (result.reason === "missing") notFound();
    return (
      <DataUnavailable
        title="Results unavailable"
        reason={result.reason}
        retryHref={`/advertiser/campaigns/${campaignId}/report`}
      />
    );
  }
  const report = result.data;
  if (report.campaign_id !== campaignId) notFound();
  return (
    <div className="animate-rise mx-auto max-w-6xl">
      <h1 className="font-display text-3xl font-semibold">Campaign results</h1>
      <p className="text-muted mt-3 text-sm">
        {report.start_at || report.end_at
          ? formatDateRange(report.start_at, report.end_at)
          : "Campaign so far"}
      </p>
      <div className="mt-6 grid grid-cols-2 gap-4 lg:grid-cols-4">
        {[
          ["Distance driven", formatKm(report.totals.distance_m)],
          ["Trips", formatCount(report.totals.trip_count)],
          ["Days on the road", formatCount(report.totals.driving_days)],
          ["Estimated views", formatCount(report.totals.estimated_views)],
        ].map(([label, value]) => (
          <Panel key={label} className="p-5">
            <p className="text-muted text-sm">{label}</p>
            <p className="font-display mt-3 text-2xl font-semibold">{value}</p>
          </Panel>
        ))}
      </div>
      <p className="text-muted mt-5 text-sm">{report.completeness}</p>
      <p className="text-muted mt-2 text-sm">{report.uncertainty}</p>
      <PerformanceAreas areas={report.areas} />
      {report.measurement_run_id ? (
        <ReportIssuancePanel
          key={report.measurement_run_id}
          measurementRunId={report.measurement_run_id}
        />
      ) : (
        <p className="text-muted mt-6 text-sm">
          Your downloadable report will appear once it’s ready.
        </p>
      )}
    </div>
  );
}
