import type { components } from "@/lib/api/schema";

type Run = components["schemas"]["MeasurementRunSummary"];
type Result = components["schemas"]["MeasurementResultRead"];

export const FROZEN_REPORT_TIMEZONE = "UTC";
export const FROZEN_REPORT_ROUNDING = "Exact frozen decimal strings; no browser rounding.";

export type FrozenReportScreenProjection = {
  period: string;
  timezone: typeof FROZEN_REPORT_TIMEZONE;
  rounding: typeof FROZEN_REPORT_ROUNDING;
  inputSha256: string;
  resultSha256: string;
  proofSha256: string;
  reportSha256: string;
  metrics: Result["metrics"];
  roi: Result["roi"];
  roiGate: Result["roi_gate"];
};

function utcInstant(value: string): string {
  const instant = new Date(value);
  return Number.isNaN(instant.getTime()) ? value : instant.toISOString();
}

export function frozenReportScreenProjection(
  run: Run,
  result: Result,
): FrozenReportScreenProjection {
  return {
    period: `${utcInstant(run.period_start_at)} to ${utcInstant(run.period_end_at)}`,
    timezone: FROZEN_REPORT_TIMEZONE,
    rounding: FROZEN_REPORT_ROUNDING,
    inputSha256: run.input_manifest_sha256,
    resultSha256: run.result_manifest_sha256,
    proofSha256: run.proof_manifest_sha256,
    reportSha256: run.report_snapshot_sha256,
    metrics: result.metrics,
    roi: result.roi,
    roiGate: result.roi_gate,
  };
}

export function exactFrozenValue(value: string | number): string {
  return String(value);
}
