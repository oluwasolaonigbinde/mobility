import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { components } from "@/lib/api/schema";
import { MeasurementAuthorityPanel, validateMeasurementAuthority } from "./measurement-authority";

type Report = components["schemas"]["CampaignReportResponse"];
const CAMPAIGN_ID = "00000000-0000-4000-8000-000000000009";

function reportFixture({ roi = false }: { roi?: boolean } = {}): Report {
  const run = {
    id: "00000000-0000-4000-8000-000000000001",
    mode: roi ? ("roi_enabled" as const) : ("performance_only" as const),
    formula_version: "measurement-result-v1",
    method_revision: "measurement-contract-v1",
    roi_method_revision: roi ? "synthetic-roi-v1" : null,
    period_start_at: "2026-08-01T00:00:00Z",
    period_end_at: "2026-08-02T00:00:00Z",
    input_manifest_sha256: "a".repeat(64),
    result_manifest_sha256: "b".repeat(64),
    proof_manifest_sha256: "c".repeat(64),
    report_snapshot_sha256: "d".repeat(64),
    reissue_of_run_id: null,
    created_at: "2026-08-03T00:00:00Z",
  };
  const result = {
    schema_version: "measurement-result-v1" as const,
    title: "Campaign Performance Analysis" as const,
    mode: run.mode,
    formula_version: run.formula_version,
    method_revision: run.method_revision,
    period: { start_at: run.period_start_at, end_at: run.period_end_at },
    proof_manifest_sha256: run.proof_manifest_sha256,
    metrics: [
      {
        id: "verified_vehicle_movement" as const,
        label: "Verified vehicle movement" as const,
        class: "measured_operational_fact" as const,
        trip_count: 4,
        distance_m: "12000.00",
        active_tracking_seconds: 3600,
      },
      {
        id: "modelled_potential_contacts" as const,
        label: "Modelled potential contacts" as const,
        class: "modelled_measure" as const,
        value: "900.00",
        formula_versions: ["impressions_v1"],
        uncertainty: "Modelled value; not observed people or attributed conversions.",
      },
      {
        id: "driver_campaign_cost" as const,
        label: "Driver campaign cost" as const,
        class: "measured_financial_fact" as const,
        totals_by_currency: [{ currency: "NGN", value: "1200.00" }],
      },
    ],
    roi: roi
      ? {
          label: "Return on investment" as const,
          class: "conditional_financial_measure" as const,
          ratio: "1",
          percent: "100",
          currency: "NGN",
          method_revision: "synthetic-roi-v1",
        }
      : null,
    roi_gate: roi
      ? ({ decision: "INCLUDE", test_only: true } as const)
      : ({ decision: "OMIT" } as const),
  };
  return {
    campaign_id: CAMPAIGN_ID,
    measurement_run: run,
    measurement_result: result,
  } as unknown as Report;
}

function readyZoneReport(): Report {
  const report = reportFixture();
  report.exposure_score = {
    formula_version: "exposure_v1",
    formula_fingerprint: "e".repeat(64),
    input_fingerprint: "f".repeat(64),
    result_fingerprint: "1".repeat(64),
    measurement_input_sha256: "a".repeat(64),
    measurement_result_sha256: "b".repeat(64),
    measurement_proof_sha256: "c".repeat(64),
    reproducible: true,
    stale: false,
    result: {
      formula_version: "exposure_v1",
      formula_fingerprint: "e".repeat(64),
      input_fingerprint: "f".repeat(64),
      status: "scored",
      score: "84.00",
      provenance: {
        measurement_run_id: report.measurement_run!.id,
        measurement_input_sha256: "a".repeat(64),
        measurement_result_sha256: "b".repeat(64),
        measurement_proof_sha256: "c".repeat(64),
      },
    },
  } as components["schemas"]["AdvertiserExposureScoreRead"];
  report.high_exposure_zone_insights = {
    state: "ready",
    campaign_id: CAMPAIGN_ID,
    campaign_exposure_score: "84.00",
    items: [
      {
        rank: 1,
        zone_id: "00000000-0000-4000-8000-000000000010",
        zone_name: "Central Abuja",
        modelled_potential_contacts: "900.00",
        trip_count: 4,
      },
    ],
    provenance: {
      formula_version: "high_exposure_zone_v1",
      formula_fingerprint: "2".repeat(64),
      measurement_run_id: report.measurement_run!.id,
      exposure_score_id: "00000000-0000-4000-8000-000000000011",
      exposure_formula_version: "exposure_v1",
      exposure_formula_fingerprint: "e".repeat(64),
      exposure_input_fingerprint: "f".repeat(64),
      source_segments: [
        {
          segment_id: "00000000-0000-4000-8000-000000000012",
          segment_version: 1,
          segment_snapshot_sha256: "3".repeat(64),
          reissue_of_segment_id: null,
        },
      ],
    },
    uncertainty: null,
    disclaimer: "Disclosure-cleared frozen ranking.",
  };
  return report;
}

describe("frozen measurement authority", () => {
  it("renders performance analysis with no ROI wording when the frozen gate omits it", () => {
    const report = reportFixture();
    const authority = validateMeasurementAuthority(report);
    expect(authority.ok).toBe(true);

    render(<MeasurementAuthorityPanel authority={authority} />);

    expect(screen.getByText("Verified vehicle movement")).toBeInTheDocument();
    expect(screen.getByText("Modelled potential contacts")).toBeInTheDocument();
    expect(screen.getByText("Driver campaign cost")).toBeInTheDocument();
    expect(screen.queryByText(/ROI/i)).not.toBeInTheDocument();
  });

  it("renders a test-only ROI section only for a fully consistent included result", () => {
    const authority = validateMeasurementAuthority(reportFixture({ roi: true }));
    expect(authority.ok).toBe(true);

    render(<MeasurementAuthorityPanel authority={authority} />);

    expect(screen.getByText("Return on investment")).toBeInTheDocument();
    expect(screen.getByText("100.00%")).toBeInTheDocument();
    expect(screen.getByText(/synthetic test-only result/i)).toBeInTheDocument();
  });

  it("rejects missing or contradictory frozen run, result, proof and ROI fields", () => {
    const missing = reportFixture();
    missing.measurement_run = null;
    expect(validateMeasurementAuthority(missing).ok).toBe(false);

    const proofMismatch = reportFixture();
    proofMismatch.measurement_result!.proof_manifest_sha256 = "e".repeat(64);
    expect(validateMeasurementAuthority(proofMismatch).ok).toBe(false);

    const contradictoryRoi = reportFixture({ roi: true });
    contradictoryRoi.measurement_run!.roi_method_revision = "different-method";
    expect(validateMeasurementAuthority(contradictoryRoi).ok).toBe(false);
  });

  it("requires complete matching score and ready-zone lineage", () => {
    expect(validateMeasurementAuthority(readyZoneReport()).ok).toBe(true);

    const missingScore = readyZoneReport();
    missingScore.exposure_score = null;
    expect(validateMeasurementAuthority(missingScore).ok).toBe(false);

    const scoreMismatch = readyZoneReport();
    scoreMismatch.exposure_score!.result.input_fingerprint = "4".repeat(64);
    expect(validateMeasurementAuthority(scoreMismatch).ok).toBe(false);

    const zoneMismatch = readyZoneReport();
    zoneMismatch.high_exposure_zone_insights!.provenance!.exposure_formula_fingerprint = "5".repeat(
      64,
    );
    expect(validateMeasurementAuthority(zoneMismatch).ok).toBe(false);

    const brokenRanking = readyZoneReport();
    brokenRanking.high_exposure_zone_insights!.items[0]!.rank = 2;
    expect(validateMeasurementAuthority(brokenRanking).ok).toBe(false);
  });
});
