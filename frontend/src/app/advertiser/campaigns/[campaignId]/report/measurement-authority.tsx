import type { components } from "@/lib/api/schema";
import { formatCount, formatDate, formatKm, formatMoney } from "@/lib/format";
import { Panel } from "@/components/ui/panel";
import { StatusChip } from "@/components/ui/status-chip";

type Report = components["schemas"]["CampaignReportResponse"];
type Run = components["schemas"]["MeasurementRunSummary"];
type Result = components["schemas"]["MeasurementResultRead"];
type Metric = Result["metrics"][number];
type Completeness = components["schemas"]["MeasurementCompletenessRead"];

export type ModelledContactsMetric = Extract<Metric, { id: "modelled_potential_contacts" }>;
export type CostMetric = Extract<Metric, { id: "driver_campaign_cost" }>;
export type MovementMetric = Extract<Metric, { id: "verified_vehicle_movement" }>;

// Matches completeness_rule.omitted_label in docs/measurement-methodology.json and
// SUPPRESSED_TOTAL_LABEL in app/services/measurement.py, so all three surfaces agree.
export const OMITTED_TOTAL_LABEL = "Omitted - insufficient frozen evidence";

export function modelledContactsMetric(result: Result): ModelledContactsMetric | undefined {
  return result.metrics.find(
    (metric): metric is ModelledContactsMetric => metric.id === "modelled_potential_contacts",
  );
}

export function costMetric(result: Result): CostMetric | undefined {
  return result.metrics.find(
    (metric): metric is CostMetric => metric.id === "driver_campaign_cost",
  );
}

export function movementMetric(result: Result): MovementMetric | undefined {
  return result.metrics.find(
    (metric): metric is MovementMetric => metric.id === "verified_vehicle_movement",
  );
}

export function costMetricDisplay(metric: CostMetric): string {
  if (metric.completeness.suppressed || metric.totals_by_currency.length === 0) {
    return OMITTED_TOTAL_LABEL;
  }
  return metric.totals_by_currency
    .map((total) => formatMoney(total.value, total.currency))
    .join(" · ");
}

export type MeasurementAuthority =
  | { ok: true; run: Run; result: Result; roiIncluded: boolean; testOnlyRoi: boolean }
  | { ok: false; reason: string };

function sameInstant(left: string, right: string): boolean {
  const leftTime = Date.parse(left);
  const rightTime = Date.parse(right);
  return Number.isFinite(leftTime) && Number.isFinite(rightTime) && leftTime === rightTime;
}

function completenessCopy(value: Completeness): string {
  const marker = value.suppressed
    ? " · total omitted rather than zero-filled"
    : value.complete
      ? ""
      : " · period incomplete";
  return `${formatCount(value.covered_trip_count)} of ${formatCount(value.denominator_trip_count)} completed trips covered · ${formatCount(value.insufficient_data_trip_count)} insufficient-data · ${formatCount(value.excluded_trip_count)} excluded · ${formatCount(value.in_progress_trip_count)} still in progress${marker}`;
}

export function validateMeasurementAuthority(report: Report): MeasurementAuthority {
  const run = report.measurement_run;
  const result = report.measurement_result;
  if (!run || !result) {
    return { ok: false, reason: "A frozen measurement run and result are required." };
  }
  if (
    result.title !== "Campaign Performance Analysis" ||
    result.schema_version !== "measurement-result-v1" ||
    result.mode !== run.mode ||
    result.formula_version !== run.formula_version ||
    result.method_revision !== run.method_revision ||
    result.proof_manifest_sha256 !== run.proof_manifest_sha256 ||
    !sameInstant(result.period.start_at, run.period_start_at) ||
    !sameInstant(result.period.end_at, run.period_end_at)
  ) {
    return { ok: false, reason: "The frozen run and result provenance do not agree." };
  }
  const metricIds = result.metrics.map((metric) => metric.id);
  if (
    metricIds.length !== 3 ||
    new Set(metricIds).size !== 3 ||
    !metricIds.includes("verified_vehicle_movement") ||
    !metricIds.includes("modelled_potential_contacts") ||
    !metricIds.includes("driver_campaign_cost")
  ) {
    return { ok: false, reason: "The frozen performance result is incomplete." };
  }

  const includesRoi = result.roi_gate.decision === "INCLUDE";
  if (
    includesRoi !== (result.roi !== null) ||
    (includesRoi &&
      (run.mode !== "roi_enabled" ||
        !run.roi_method_revision ||
        result.roi?.method_revision !== run.roi_method_revision)) ||
    (!includesRoi && (run.mode !== "performance_only" || run.roi_method_revision !== null))
  ) {
    return { ok: false, reason: "The frozen financial-result gate is inconsistent." };
  }

  const score = report.exposure_score;
  if (
    score &&
    (score.formula_version !== score.result.formula_version ||
      score.formula_fingerprint !== score.result.formula_fingerprint ||
      score.input_fingerprint !== score.result.input_fingerprint ||
      score.result.provenance.measurement_run_id !== run.id ||
      score.result.provenance.measurement_input_sha256 !== run.input_manifest_sha256 ||
      score.result.provenance.measurement_result_sha256 !== run.result_manifest_sha256 ||
      score.result.provenance.measurement_proof_sha256 !== run.proof_manifest_sha256 ||
      score.measurement_input_sha256 !== run.input_manifest_sha256 ||
      score.measurement_result_sha256 !== run.result_manifest_sha256 ||
      score.measurement_proof_sha256 !== run.proof_manifest_sha256 ||
      !score.reproducible ||
      score.stale)
  ) {
    return { ok: false, reason: "The exposure score belongs to a different measurement run." };
  }
  const zoneInsight = report.high_exposure_zone_insights;
  const readyZoneIds =
    zoneInsight?.state === "ready" ? zoneInsight.items.map((item) => item.zone_id) : [];
  if (
    zoneInsight?.state === "ready" &&
    (!zoneInsight.provenance ||
      !score ||
      score.result.status !== "scored" ||
      score.result.score === null ||
      zoneInsight.campaign_id !== report.campaign_id ||
      zoneInsight.items.length === 0 ||
      new Set(readyZoneIds).size !== readyZoneIds.length ||
      !zoneInsight.items.every((item, index) => item.rank === index + 1) ||
      zoneInsight.provenance.source_segments.length === 0 ||
      zoneInsight.provenance.measurement_run_id !== run.id ||
      zoneInsight.provenance.exposure_formula_version !== score.formula_version ||
      zoneInsight.provenance.exposure_formula_fingerprint !== score.formula_fingerprint ||
      zoneInsight.provenance.exposure_input_fingerprint !== score.input_fingerprint ||
      zoneInsight.campaign_exposure_score !== score.result.score)
  ) {
    return { ok: false, reason: "The zone projection belongs to a different measurement run." };
  }

  return {
    ok: true,
    run,
    result,
    roiIncluded: includesRoi,
    testOnlyRoi: includesRoi && result.roi_gate.decision === "INCLUDE" && result.roi_gate.test_only,
  };
}

export function MeasurementAuthorityPanel({ authority }: { authority: MeasurementAuthority }) {
  if (!authority.ok) return null;
  const { run, result } = authority;

  return (
    <Panel className="mt-6 p-6" aria-label="Frozen measurement authority">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="micro text-amber">Frozen measurement authority</p>
          <h2 className="mt-1 font-medium">Verified and modelled results</h2>
          <p className="text-muted mt-1 text-sm">
            {formatDate(result.period.start_at)} → {formatDate(result.period.end_at)} · no client
            recalculation
          </p>
        </div>
        <StatusChip tone="green">reproducible</StatusChip>
      </div>

      <div className="mt-5 grid gap-4 md:grid-cols-3">
        {result.metrics.map((metric) => {
          if (metric.id === "verified_vehicle_movement") {
            return (
              <div key={metric.id}>
                <p className="micro text-muted">{metric.label}</p>
                <p className="mt-1 text-lg font-medium">
                  {metric.distance_m === null ? OMITTED_TOTAL_LABEL : formatKm(metric.distance_m)}
                </p>
                <p className="text-faint mt-1 text-xs">
                  {formatCount(metric.trip_count)} governed trips ·{" "}
                  {metric.active_tracking_seconds === null
                    ? "tracking total omitted"
                    : `${metric.active_tracking_seconds} s active tracking`}
                </p>
                <p className="text-faint mt-2 text-xs">{completenessCopy(metric.completeness)}</p>
                <p className="text-muted mt-2 text-xs">{metric.uncertainty}</p>
              </div>
            );
          }
          if (metric.id === "modelled_potential_contacts") {
            return (
              <div key={metric.id}>
                <p className="micro text-muted">{metric.label}</p>
                <p className="mt-1 text-lg font-medium">
                  {metric.value === null ? OMITTED_TOTAL_LABEL : formatCount(metric.value)}
                </p>
                <p className="text-faint mt-1 text-xs">{metric.uncertainty}</p>
                <p className="text-faint mt-2 text-xs">{completenessCopy(metric.completeness)}</p>
                <details className="text-faint mt-2 text-xs">
                  <summary>Density parameter provenance</summary>
                  <p className="mt-1">Source: {metric.density_provenance.source}</p>
                  <p>Calibration: {metric.density_provenance.calibration}</p>
                  {metric.density_provenance.profiles.map((profile) => (
                    <p key={`${profile.lineage_id}:${profile.revision}`} className="mt-1 font-mono">
                      profile {profile.profile_id} · lineage {profile.lineage_id} · revision{" "}
                      {profile.revision} · effective {profile.effective_from} ·{" "}
                      {profile.traffic_density_per_km}/km · {profile.dwell_impressions_per_minute}
                      /dwell-minute · {profile.road_category_method} · {profile.value_fingerprint}
                    </p>
                  ))}
                </details>
              </div>
            );
          }
          return (
            <div key={metric.id}>
              <p className="micro text-muted">{metric.label}</p>
              <p className="mt-1 text-lg font-medium">{costMetricDisplay(metric)}</p>
              <p className="text-faint mt-1 text-xs">Measured campaign operating cost</p>
              <p className="text-faint mt-2 text-xs">{completenessCopy(metric.completeness)}</p>
            </div>
          );
        })}
      </div>

      {authority.roiIncluded && result.roi ? (
        <div className="border-edge mt-5 border-t pt-5" aria-label="Conditional financial result">
          <div className="flex flex-wrap items-center gap-3">
            <h3 className="font-medium">{result.roi.label}</h3>
            {authority.testOnlyRoi ? (
              <StatusChip tone="amber">synthetic test-only result</StatusChip>
            ) : null}
          </div>
          <p className="mt-2 text-2xl font-semibold">{Number(result.roi.percent).toFixed(2)}%</p>
          <p className="micro text-faint mt-1 font-mono">
            {result.roi.currency} · method {result.roi.method_revision}
          </p>
          <dl className="text-muted mt-3 grid gap-2 text-xs md:grid-cols-2">
            <div>
              <dt className="font-medium">Approval</dt>
              <dd>{result.roi.method.approval_reference}</dd>
            </div>
            <div>
              <dt className="font-medium">Attribution rule</dt>
              <dd>{result.roi.method.attribution_rule}</dd>
            </div>
            <div>
              <dt className="font-medium">Attribution window</dt>
              <dd>{result.roi.method.attribution_window}</dd>
            </div>
            <div>
              <dt className="font-medium">Cost basis</dt>
              <dd>{result.roi.method.cost_basis}</dd>
            </div>
            <div>
              <dt className="font-medium">Exclusions</dt>
              <dd>{result.roi.method.exclusions}</dd>
            </div>
            <div>
              <dt className="font-medium">Corrections</dt>
              <dd>{result.roi.method.corrections}</dd>
            </div>
            <div>
              <dt className="font-medium">Late data</dt>
              <dd>{result.roi.method.late_data}</dd>
            </div>
            <div>
              <dt className="font-medium">Reporting cutoff</dt>
              <dd>{result.roi.provenance.reporting_cutoff}</dd>
            </div>
            <div>
              <dt className="font-medium">Conversion provenance</dt>
              <dd>{result.roi.provenance.conversion_provenance}</dd>
            </div>
            <div>
              <dt className="font-medium">Revenue provenance</dt>
              <dd>{result.roi.provenance.revenue_provenance}</dd>
            </div>
          </dl>
          <p className="text-muted mt-3 text-xs">{result.roi.method.limitations}</p>
        </div>
      ) : null}

      <div className="border-edge mt-5 border-t pt-4 font-mono text-xs">
        <p className="text-muted">Run {run.id}</p>
        <p className="text-faint mt-1">
          result {run.result_manifest_sha256.slice(0, 16)}… · proof{" "}
          {run.proof_manifest_sha256.slice(0, 16)}… · report{" "}
          {run.report_snapshot_sha256.slice(0, 16)}…
        </p>
      </div>
    </Panel>
  );
}

const stateCopy: Record<string, { title: string; body: string }> = {
  SAFE_MEASUREMENT_RUN_REQUIRED: {
    title: "No frozen analysis is available",
    body: "An immutable measurement run must be issued before campaign results can be shown.",
  },
  MEASUREMENT_LIVE_ISSUANCE_BLOCKED: {
    title: "Live analysis is unavailable",
    body: "The approved reporting method and live-use gates are not complete for this deployment.",
  },
  MEASUREMENT_RUN_INTEGRITY_FAILURE: {
    title: "Frozen analysis failed its integrity check",
    body: "No campaign result is shown. Issue a new governed measurement run after correcting the source authority.",
  },
  EXPOSURE_SCORE_INTEGRITY_FAILURE: {
    title: "Exposure analysis failed its integrity check",
    body: "No campaign result is shown because its score no longer agrees with the frozen run.",
  },
};

export function GovernedAnalysisState({ code }: { code: string }) {
  const copy = stateCopy[code] ?? {
    title: "Campaign analysis is unavailable",
    body: "No map or performance result is shown because the governed source could not be verified.",
  };
  return (
    <Panel role="status" className="border-amber/40 bg-amber/5 mx-auto max-w-3xl p-6">
      <p className="micro text-amber">Fail-closed reporting state</p>
      <h1 className="mt-2 text-xl font-semibold">{copy.title}</h1>
      <p className="text-muted mt-2 text-sm">{copy.body}</p>
      <p className="micro text-faint mt-3 font-mono">{code}</p>
    </Panel>
  );
}
