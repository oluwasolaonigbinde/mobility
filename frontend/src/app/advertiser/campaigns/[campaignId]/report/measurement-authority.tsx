import type { components } from "@/lib/api/schema";
import { formatCount, formatKm, formatDuration, formatMoneyExact } from "@/lib/format";
import { Panel } from "@/components/ui/panel";
import { exactFrozenValue, frozenReportScreenProjection } from "./frozen-report-projection";

type Report = components["schemas"]["CampaignReportResponse"];
type Run = components["schemas"]["MeasurementRunSummary"];
type Result = components["schemas"]["MeasurementResultRead"];
type Metric = Result["metrics"][number];
type Completeness = components["schemas"]["MeasurementCompletenessRead"];

export type ModelledContactsMetric = Extract<Metric, { id: "modelled_potential_contacts" }>;
export type CostMetric = Extract<Metric, { id: "driver_campaign_cost" }>;
export type MovementMetric = Extract<Metric, { id: "verified_vehicle_movement" }>;

// Screen-only wording. The detailed CSV/PDF labels remain unchanged.
export const OMITTED_TOTAL_LABEL = "Not enough data";

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
    .map((total) => formatMoneyExact(total.value, total.currency))
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
  if (
    value.complete &&
    !value.suppressed &&
    !value.insufficient_data_trip_count &&
    !value.excluded_trip_count &&
    !value.in_progress_trip_count
  )
    return `Based on all ${formatCount(value.denominator_trip_count)} completed trips`;
  const parts = [
    `Based on ${formatCount(value.covered_trip_count)} of ${formatCount(value.denominator_trip_count)} completed trips`,
  ];
  if (value.insufficient_data_trip_count)
    parts.push(`${formatCount(value.insufficient_data_trip_count)} with too little data`);
  if (value.excluded_trip_count) parts.push(`${formatCount(value.excluded_trip_count)} excluded`);
  if (value.in_progress_trip_count)
    parts.push(`${formatCount(value.in_progress_trip_count)} still in progress`);
  return parts.join(" · ");
}
export function reportPeriod(start: string, end: string): string {
  const fmt = new Intl.DateTimeFormat("en-GB", {
    day: "numeric",
    month: "short",
    year: "numeric",
    timeZone: "Africa/Lagos",
  });
  return fmt.formatRange(new Date(start), new Date(end)).replace(/\u2009/g, " ");
}

/**
 * No analysis has been issued yet: neither half of a frozen run exists. Only a
 * present but disagreeing run/result is an integrity failure.
 */
export function isUnissued(report: Report): boolean {
  return !report.measurement_run && !report.measurement_result;
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

export function MeasurementAuthorityPanel({
  authority,
  activityScore = null,
}: {
  authority: MeasurementAuthority;
  activityScore?: string | null;
}) {
  if (!authority.ok) return null;
  const { run, result } = authority;
  const projection = frozenReportScreenProjection(run, result);

  const movement = movementMetric(result)!;
  const contacts = modelledContactsMetric(result)!;
  const cost = costMetric(result)!;
  const sameCompleteness = result.metrics.every((metric) =>
    (Object.keys(contacts.completeness) as (keyof Completeness)[]).every(
      (key) => metric.completeness[key] === contacts.completeness[key],
    ),
  );
  return (
    <Panel className="mt-6 p-6" aria-label="Report basis">
      <p className="micro text-amber">Campaign results</p>
      <h2 className="mt-1 font-medium">
        {reportPeriod(result.period.start_at, result.period.end_at)}
      </h2>
      <p className="text-faint mt-1 text-xs">Nigeria time (WAT)</p>
      {sameCompleteness ? (
        <p className="text-muted mt-4 text-sm">{completenessCopy(contacts.completeness)}</p>
      ) : (
        <div className="text-muted mt-4 space-y-1 text-sm">
          <p>Distance: {completenessCopy(movement.completeness)}</p>
          <p>Ad exposure: {completenessCopy(contacts.completeness)}</p>
          <p>Driver cost: {completenessCopy(cost.completeness)}</p>
        </div>
      )}
      <div className="mt-5 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <div>
          <p className="micro text-muted">Distance covered</p>
          <p className="mt-1 text-lg font-medium">
            {movement.completeness.suppressed || movement.distance_m === null
              ? OMITTED_TOTAL_LABEL
              : formatKm(movement.distance_m)}
          </p>
          <p className="text-faint mt-1 text-xs">
            {movement.completeness.suppressed || movement.active_tracking_seconds === null
              ? "Tracking time unavailable"
              : `${formatDuration(movement.active_tracking_seconds)} of tracking`}
          </p>
        </div>
        <div>
          <p className="micro text-muted">Estimated ad exposure</p>
          <p className="mt-1 text-lg font-medium">
            {contacts.completeness.suppressed || contacts.value === null
              ? OMITTED_TOTAL_LABEL
              : formatCount(contacts.value)}
          </p>
          <p className="text-faint mt-1 text-xs">Estimated opportunities to see the ad</p>
        </div>
        <div>
          <p className="micro text-muted">Driver campaign cost</p>
          <p className="mt-1 text-lg font-medium">{costMetricDisplay(cost)}</p>
          <p className="text-faint mt-1 text-xs">Driver pay for this campaign</p>
        </div>
        <div>
          <p className="micro text-muted">Campaign activity score</p>
          <p className="mt-1 text-lg font-medium">
            {activityScore !== null && Number.isFinite(Number(activityScore))
              ? `${Number(activityScore).toFixed(2)} / 100`
              : "—"}
          </p>
          <p className="text-faint mt-1 text-xs">
            Activity from distance, tracking time and route quality
          </p>
        </div>
      </div>
      <details className="text-muted mt-5 text-sm">
        <summary className="cursor-pointer">How this is calculated</summary>
        <ul className="mt-3 list-disc space-y-2 pl-5">
          <li>
            Ad exposure is estimated from routes and traffic. It is not a count of people or
            measured views.
          </li>
          <li>Model confidence describes the estimate; it is not a statistical interval.</li>
          <li>Recorded movement does not prove someone saw the ad.</li>
          <li>
            Driver campaign cost is driver pay, not your advertising spend, revenue or return.
          </li>
          <li>Missing results are left out rather than counted as zero.</li>
          <li>Areas are ranked by estimated ad exposure from this campaign’s trips.</li>
          <li>
            A trip is counted in each mapped area section and time window it visits. It can
            contribute more than once to an area’s count.
          </li>
          <li>The activity score combines distance, tracking time and route quality.</li>
        </ul>
      </details>
      {projection.roiGate.decision === "INCLUDE" && projection.roi ? (
        <div className="border-edge mt-5 border-t pt-5" aria-label="Conditional financial result">
          <h3 className="font-medium">{projection.roi.label}</h3>
          <p className="mt-2 text-2xl font-semibold">{exactFrozenValue(projection.roi.percent)}%</p>
          <p className="text-muted mt-3 text-xs">
            Based on the conversion and revenue figures supplied for this campaign.
          </p>
        </div>
      ) : null}
    </Panel>
  );
}

const stateCopy: Record<string, { title: string; body: string }> = {
  CAMPAIGN_REPORT_PENDING: {
    title: "Your campaign report is being prepared",
    body: "Check back here for your campaign results.",
  },
  ZONE_PROJECTION_UNAVAILABLE: {
    title: "The area map isn't available for this report",
    body: "The Campaign Performance Analysis page still shows the rest of the results.",
  },
  ZONE_PROJECTION_INTEGRITY_FAILURE: {
    title: "The area map doesn't match this report",
    body: "No map is shown because the area data doesn't match the issued report. Terrax Media needs to reissue the analysis.",
  },
  MEASUREMENT_RUN_INTEGRITY_FAILURE: {
    title: "This report failed its integrity check",
    body: "No campaign results are shown because the report data did not pass verification. Terrax Media needs to reissue the analysis.",
  },
  EXPOSURE_SCORE_INTEGRITY_FAILURE: {
    title: "Exposure analysis failed its integrity check",
    body: "No campaign results are shown because the exposure score does not match this report. Terrax Media needs to reissue the analysis.",
  },
};

export function GovernedAnalysisState({ code }: { code: string }) {
  const copy = stateCopy[code] ?? {
    title: "Campaign results can't be shown",
    body: "No results are shown for this campaign at the moment.",
  };
  return (
    <Panel role="status" className="border-amber/40 bg-amber/5 mx-auto max-w-3xl p-6">
      <p className="micro text-amber">Campaign results</p>
      <h1 className="mt-2 text-xl font-semibold">{copy.title}</h1>
      <p className="text-muted mt-2 text-sm">{copy.body}</p>
    </Panel>
  );
}
