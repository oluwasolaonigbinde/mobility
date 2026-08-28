import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { createApiClient } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import { getSessionToken } from "@/lib/auth/session";
import { formatCount, formatDate, formatKm, formatMoney, formatScore } from "@/lib/format";
import { statusLabel, statusTone } from "@/lib/campaigns/status";
import { Panel } from "@/components/ui/panel";
import { Stat } from "@/components/ui/stat";
import { StatusChip } from "@/components/ui/status-chip";
import { AreaTimeseries, BarTimeseries, type SeriesPoint } from "@/components/charts/timeseries";
import { MeasurementHeadlineStats } from "./measurement-headline-stats";
import { HighExposureZoneInsights } from "@/components/analytics/high-exposure-zone-insights";
import {
  GovernedAnalysisState,
  MeasurementAuthorityPanel,
  validateMeasurementAuthority,
} from "./measurement-authority";

export const metadata: Metadata = { title: "Campaign Performance Analysis" };

const shortDate = new Intl.DateTimeFormat("en-NG", { day: "numeric", month: "short" });

export default async function CampaignReportPage({
  params,
}: {
  params: Promise<{ campaignId: string }>;
}) {
  const { campaignId } = await params;
  const api = createApiClient(await getSessionToken());

  let report;
  try {
    ({ data: report } = await api.GET("/api/v1/advertiser/campaigns/{campaign_id}/report", {
      params: { path: { campaign_id: campaignId } },
    }));
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) notFound();
    return (
      <GovernedAnalysisState
        code={error instanceof ApiError ? error.code : "REPORT_SOURCE_UNAVAILABLE"}
      />
    );
  }
  if (!report) return <GovernedAnalysisState code="SAFE_MEASUREMENT_RUN_REQUIRED" />;
  const authority = validateMeasurementAuthority(report);
  if (!authority.ok) {
    return <GovernedAnalysisState code="MEASUREMENT_RUN_INTEGRITY_FAILURE" />;
  }

  const c = report.summary;
  // Daily metrics arrive newest-first; charts read left→right in time.
  const daily = [...report.daily_metrics].reverse();
  const impressionSeries: SeriesPoint[] = daily.map((d) => ({
    label: shortDate.format(new Date(d.date)),
    value: Number(d.estimated_impressions ?? 0),
  }));
  const payoutSeries: SeriesPoint[] = daily.map((d) => ({
    label: shortDate.format(new Date(d.date)),
    value: Number(d.final_payout_total ?? 0),
  }));
  const cost = report.cost_summary.totals_by_currency[0];

  return (
    <div className="animate-rise mx-auto max-w-6xl">
      <nav aria-label="Breadcrumb" className="micro text-faint mb-4">
        <Link href="/advertiser/campaigns" className="hover:text-muted">
          Campaigns
        </Link>{" "}
        /{" "}
        <Link href={`/advertiser/campaigns/${campaignId}`} className="hover:text-muted">
          {c.name}
        </Link>{" "}
        / <span className="text-muted">Report</span>
      </nav>

      <div className="mb-8 flex flex-wrap items-center gap-3">
        <h1 className="font-display text-3xl font-semibold tracking-tight">
          Campaign Performance Analysis
        </h1>
        <StatusChip tone={statusTone[c.status]}>{statusLabel[c.status]}</StatusChip>
        <span className="micro text-faint">
          {report.start_at || report.end_at
            ? `${formatDate(report.start_at)} → ${formatDate(report.end_at)}`
            : "Full campaign history"}
        </span>
      </div>

      <MeasurementAuthorityPanel authority={authority} />

      {/* Headline numbers */}
      <div className="mt-6 grid grid-cols-2 gap-4 lg:grid-cols-5">
        <MeasurementHeadlineStats
          exposureScore={
            report.exposure_score
              ? {
                  formulaVersion: report.exposure_score.formula_version,
                  formulaFingerprint: report.exposure_score.formula_fingerprint,
                  inputFingerprint: report.exposure_score.input_fingerprint,
                  status: report.exposure_score.result.status,
                  score: report.exposure_score.result.score,
                  routeCount: report.exposure_score.result.route_count,
                  missingRouteCount: report.exposure_score.result.missing_route_count,
                  uncertainty: report.exposure_score.result.uncertainty.statement,
                }
              : null
          }
          modelledPotentialContacts={report.impression_summary.estimated_impressions}
          estimatedTripCount={report.impression_summary.estimated_trip_count}
          modelDiagnostic={report.impression_summary.average_confidence_score}
        />
        <Stat
          label="Trips analyzed"
          value={formatCount(report.trip_summary.ended)}
          tone="cyan"
          hint={`${formatCount(report.trip_summary.total)} total sessions · ${formatCount(report.assignment_summary.active)} active vehicles`}
        />
        <Stat
          label="Driver campaign cost"
          value={cost ? formatMoney(cost.final_payout_total, cost.currency) : "—"}
          tone="green"
          hint={
            cost ? `${formatCount(cost.calculated_trip_count)} calculated driver trips` : undefined
          }
        />
        <Stat
          label="Open fraud flags"
          value={formatCount(report.fraud_summary.open)}
          tone={report.fraud_summary.open > 0 ? "coral" : "green"}
          hint="Flagged delivery quality — billing is tracked separately"
        />
      </div>

      {report.high_exposure_zone_insights ? (
        <div className="mt-6">
          <HighExposureZoneInsights insight={report.high_exposure_zone_insights} surface="report" />
        </div>
      ) : null}

      {/* Charts */}
      <div className="mt-6 grid gap-6 lg:grid-cols-2">
        <Panel className="p-6">
          <h2 className="micro text-muted mb-1">Modelled potential contacts · daily</h2>
          <p className="text-faint mb-4 text-xs">
            Modelled from verified vehicle movement · impressions_v1
          </p>
          <AreaTimeseries
            points={impressionSeries}
            color="var(--color-amber)"
            ariaLabel="Daily modelled potential contacts"
          />
        </Panel>
        <Panel className="p-6">
          <h2 className="micro text-muted mb-1">Driver campaign cost · daily</h2>
          <p className="text-faint mb-4 text-xs">Driver payouts attributed to this campaign</p>
          <BarTimeseries
            points={payoutSeries}
            color="var(--color-green)"
            currency={cost?.currency ?? "NGN"}
            ariaLabel="Daily driver campaign cost"
          />
        </Panel>
      </div>

      {/* Daily table — the accessible source of truth for the charts */}
      <Panel className="mt-6 overflow-hidden">
        <div className="border-edge border-b px-6 py-4">
          <h2 className="micro text-muted">Daily breakdown</h2>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[720px] text-sm">
            <thead>
              <tr className="border-edge micro text-muted border-b text-left">
                <th className="px-6 py-3 font-normal">Date</th>
                <th className="px-4 py-3 text-right font-normal">Trips</th>
                <th className="px-4 py-3 text-right font-normal">Distance</th>
                <th className="px-4 py-3 text-right font-normal">Modelled contacts</th>
                <th className="px-4 py-3 text-right font-normal">Model diagnostic</th>
                <th className="px-4 py-3 text-right font-normal">Quality</th>
                <th className="px-4 py-3 text-right font-normal">Driver cost</th>
                <th className="px-6 py-3 text-right font-normal">Flags</th>
              </tr>
            </thead>
            <tbody>
              {report.daily_metrics.length === 0 ? (
                <tr>
                  <td colSpan={8} className="text-muted px-6 py-10 text-center">
                    No daily metrics yet — data appears once trips are analyzed.
                  </td>
                </tr>
              ) : (
                report.daily_metrics.map((d) => (
                  <tr
                    key={d.date}
                    className="border-edge/60 border-b font-mono text-xs last:border-0"
                  >
                    <td className="px-6 py-3">{formatDate(d.date)}</td>
                    <td className="px-4 py-3 text-right">{d.trip_count}</td>
                    <td className="px-4 py-3 text-right">{formatKm(d.distance_m)}</td>
                    <td className="px-4 py-3 text-right">{formatCount(d.estimated_impressions)}</td>
                    <td className="px-4 py-3 text-right">
                      {formatScore(d.average_confidence_score)}
                    </td>
                    <td className="px-4 py-3 text-right">{formatScore(d.average_quality_score)}</td>
                    <td className="px-4 py-3 text-right">
                      {formatMoney(d.final_payout_total, cost?.currency ?? "NGN")}
                    </td>
                    <td className="px-6 py-3 text-right">
                      {d.open_fraud_flag_count > 0 ? (
                        <span className="text-coral">{d.open_fraud_flag_count}</span>
                      ) : (
                        "0"
                      )}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </Panel>
    </div>
  );
}
