import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { components } from "@/lib/api/schema";
import {
  costMetric,
  costMetricDisplay,
  MeasurementAuthorityPanel,
  modelledContactsMetric,
  validateMeasurementAuthority,
  reportPeriod,
} from "./measurement-authority";
import { frozenReportScreenProjection } from "./frozen-report-projection";

type Report = components["schemas"]["CampaignReportResponse"];
const CAMPAIGN_ID = "00000000-0000-4000-8000-000000000009";
const COMPLETENESS = {
  cohort_trip_count: 4,
  denominator_trip_count: 4,
  in_progress_trip_count: 0,
  covered_trip_count: 4,
  insufficient_data_trip_count: 0,
  excluded_trip_count: 0,
  complete: true,
  suppressed: false,
};
const MOVEMENT_CAVEAT =
  "Completeness and quality scores describe collection quality; movement does not prove that a person saw an advert.";

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
        label: "Distance covered" as const,
        class: "measured_operational_fact" as const,
        trip_count: 4,
        distance_m: "12000.00",
        active_tracking_seconds: 3600,
        completeness: COMPLETENESS,
        uncertainty: MOVEMENT_CAVEAT,
      },
      {
        id: "modelled_potential_contacts" as const,
        label: "Modelled potential contacts" as const,
        class: "modelled_measure" as const,
        value: "900.00",
        formula_versions: ["impressions_v1"],
        completeness: COMPLETENESS,
        density_provenance: {
          source:
            "impressions_v1 output over verified vehicle movement and the applicable traffic profile",
          calibration: "Configured defaults; no independent field calibration.",
          profiles: [
            {
              profile_id: "00000000-0000-4000-8000-000000000020",
              lineage_id: "00000000-0000-4000-8000-000000000021",
              revision: "2",
              effective_from: "2026-07-01T00:00:00Z",
              value_fingerprint: "9".repeat(64),
              traffic_density_per_km: "180",
              dwell_impressions_per_minute: "12",
              road_category_method: "profile_default_weight_no_road_classification_v1",
            },
          ],
        },
        uncertainty: "Modelled value; not observed people or attributed conversions.",
      },
      {
        id: "driver_campaign_cost" as const,
        label: "Driver campaign cost" as const,
        class: "measured_financial_fact" as const,
        totals_by_currency: [{ currency: "NGN", value: "1200.00" }],
        completeness: COMPLETENESS,
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
          method: {
            approval_reference: "SYNTHETIC_TEST_ONLY",
            attribution_rule: "Synthetic campaign conversion rule.",
            attribution_window: "Synthetic one-day window.",
            cost_basis: "Frozen driver campaign cost.",
            exclusions: "No synthetic exclusions.",
            corrections: "Reissue after correction.",
            late_data: "Late data requires reissue.",
            limitations: "Advertiser-supplied inputs are not verified by Cardvert.",
          },
          provenance: {
            conversion_provenance: "SYNTHETIC_TEST_ONLY conversion fixture",
            revenue_provenance: "SYNTHETIC_TEST_ONLY revenue fixture",
            reporting_cutoff: "2026-08-02T00:00:00Z",
            synthetic: true,
          },
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
  it("keeps every screen field inside the typed frozen report projection", () => {
    const report = reportFixture({ roi: true });
    const projection = frozenReportScreenProjection(
      report.measurement_run!,
      report.measurement_result!,
    );

    expect(projection.metrics).toEqual(report.measurement_result!.metrics);
    expect(projection.roi).toEqual(report.measurement_result!.roi);
    expect(projection.roiGate).toEqual(report.measurement_result!.roi_gate);
    expect(projection).toMatchObject({
      timezone: "UTC",
      rounding: "Exact frozen decimal strings; no browser rounding.",
      inputSha256: "a".repeat(64),
      resultSha256: "b".repeat(64),
      proofSha256: "c".repeat(64),
      reportSha256: "d".repeat(64),
    });
  });

  it("renders performance analysis with no ROI wording when the frozen gate omits it", () => {
    const report = reportFixture();
    const authority = validateMeasurementAuthority(report);
    expect(authority.ok).toBe(true);

    render(<MeasurementAuthorityPanel authority={authority} />);

    expect(screen.getByLabelText("Report basis")).toBeInTheDocument();
    expect(screen.queryByText(/frozen measurement authority/i)).not.toBeInTheDocument();
    expect(screen.getByText("Distance covered")).toBeInTheDocument();
    expect(screen.getByText("Estimated ad exposure")).toBeInTheDocument();

    expect(screen.getByText(/not your advertising spend/i)).toBeInTheDocument();
    expect(screen.queryByText(/governed trips|no client recalculation/i)).not.toBeInTheDocument();
    expect(screen.getByText("Driver campaign cost")).toBeInTheDocument();
    expect(screen.getByText(/Recorded movement does not prove/)).toBeInTheDocument();
    expect(screen.getAllByText("Based on all 4 completed trips")).toHaveLength(1);

    expect(screen.getByText(/1\s*–\s*2 Aug 2026/i)).toBeInTheDocument();
    // D38(c): run IDs, manifest hashes and profile fingerprints stay off advertiser screens.
    const panel = screen.getByLabelText("Report basis");
    expect(panel.textContent).not.toMatch(
      /[0-9a-f]{64}|Technical reference|lineage|profile [0-9a-f-]{8}/i,
    );
    expect(panel.textContent).not.toContain(authority.ok ? authority.run.id : "");
    expect(screen.queryByText(/ROI/i)).not.toBeInTheDocument();
  });

  it("renders ROI only for a fully consistent included result without internal labels", () => {
    const authority = validateMeasurementAuthority(reportFixture({ roi: true }));
    expect(authority.ok).toBe(true);

    render(<MeasurementAuthorityPanel authority={authority} />);

    expect(screen.getByText("Return on investment")).toBeInTheDocument();
    expect(screen.getByText("100%")).toBeInTheDocument();
    expect(screen.queryByText(/synthetic test-only result/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/Synthetic campaign/)).not.toBeInTheDocument();
    expect(screen.queryByText(/SYNTHETIC_TEST_ONLY/)).not.toBeInTheDocument();
    expect(screen.getByText(/Based on the conversion and revenue/)).toBeInTheDocument();
  });

  it("omits an unsupported headline instead of displaying a fabricated zero", () => {
    const report = reportFixture();
    const contacts = report.measurement_result!.metrics.find(
      (metric) => metric.id === "modelled_potential_contacts",
    );
    if (!contacts || contacts.id !== "modelled_potential_contacts") throw new Error("fixture");
    contacts.value = null;
    contacts.completeness = {
      ...contacts.completeness,
      covered_trip_count: 0,
      insufficient_data_trip_count: 4,
      complete: false,
      suppressed: true,
    };

    const authority = validateMeasurementAuthority(report);
    expect(authority.ok).toBe(true);
    render(<MeasurementAuthorityPanel authority={authority} />);

    expect(screen.getByText("Not enough data")).toBeInTheDocument();
    expect(screen.queryByText(/^0$/)).not.toBeInTheDocument();
  });

  it("uses the frozen omission label for a suppressed driver-cost total", () => {
    const report = reportFixture();
    const cost = report.measurement_result!.metrics.find(
      (metric) => metric.id === "driver_campaign_cost",
    );
    if (!cost || cost.id !== "driver_campaign_cost") throw new Error("fixture");
    cost.totals_by_currency = [];
    cost.completeness = { ...cost.completeness, covered_trip_count: 0, suppressed: true };

    const authority = validateMeasurementAuthority(report);
    expect(authority.ok).toBe(true);
    render(<MeasurementAuthorityPanel authority={authority} />);

    expect(screen.getByText("Not enough data")).toBeInTheDocument();
    expect(screen.getByText("Driver campaign cost").parentElement).not.toHaveTextContent("—");
  });

  it("publishes every frozen driver-cost currency without combining their values", () => {
    const report = reportFixture();
    const cost = costMetric(report.measurement_result!);
    if (!cost) throw new Error("fixture");
    cost.totals_by_currency.push({ currency: "USD", value: "12.50" });

    const display = costMetricDisplay(cost);

    expect(display).toContain("₦1,200.00");
    expect(display).toContain("US$12.50");
    expect(display).toContain(" · ");
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

describe("frozen metric selectors", () => {
  it("returns the frozen contacts and cost metrics the headline publishes", () => {
    const result = reportFixture().measurement_result!;

    expect(modelledContactsMetric(result)?.value).toBe("900.00");
    expect(costMetric(result)?.totals_by_currency).toEqual([{ currency: "NGN", value: "1200.00" }]);
    expect(costMetric(result)?.completeness.suppressed).toBe(false);
  });
});

it("formats the report dates in Nigeria across UTC midnight", () => {
  expect(reportPeriod("2026-09-19T23:30:00Z", "2026-10-02T23:30:00Z")).toBe("20 Sept – 3 Oct 2026");
});
it("formats measured units and keeps detailed caveats collapsed", () => {
  const report = reportFixture();
  const movement = report.measurement_result!.metrics[0]!;
  if (movement.id !== "verified_vehicle_movement") throw Error("fixture");
  movement.distance_m = "200397.73";
  movement.active_tracking_seconds = 42000;
  const contacts = modelledContactsMetric(report.measurement_result!)!;
  contacts.value = "164696.13";
  const cost = costMetric(report.measurement_result!)!;
  cost.totals_by_currency = [{ currency: "NGN", value: "17504.45" }];
  render(
    <MeasurementAuthorityPanel
      authority={validateMeasurementAuthority(report)}
      activityScore="81.54"
    />,
  );
  expect(screen.getByText("200 km")).toBeInTheDocument();
  expect(screen.getAllByText("81.54 / 100")).toHaveLength(1);
  expect(screen.getByText("11h 40m of tracking")).toBeInTheDocument();
  expect(screen.getByText("164,696")).toBeInTheDocument();
  expect(screen.getByText("₦17,504.45")).toBeInTheDocument();
  expect(screen.getByText("How this is calculated").closest("details")).not.toHaveAttribute("open");
});

it("deduplicates equal completeness regardless of field order", () => {
  const report = reportFixture();
  const metric = report.measurement_result!.metrics[0]!;
  metric.completeness = Object.fromEntries(
    Object.entries(metric.completeness).reverse(),
  ) as typeof metric.completeness;
  render(<MeasurementAuthorityPanel authority={validateMeasurementAuthority(report)} />);
  expect(screen.getAllByText("Based on all 4 completed trips")).toHaveLength(1);
});

it("shows genuine zero measurements without filling missing values with zero", () => {
  const report = reportFixture();
  const metric = report.measurement_result!.metrics[0]!;
  if (metric.id !== "verified_vehicle_movement") throw Error("fixture");
  metric.distance_m = "0";
  metric.active_tracking_seconds = null;
  modelledContactsMetric(report.measurement_result!)!.value = "0";
  const cost = costMetric(report.measurement_result!)!;
  cost.totals_by_currency = [{ currency: "NGN", value: "0" }];
  render(<MeasurementAuthorityPanel authority={validateMeasurementAuthority(report)} />);
  expect(screen.getByText("0 km")).toBeInTheDocument();
  expect(screen.getByText("0")).toBeInTheDocument();
  expect(screen.getByText("₦0.00")).toBeInTheDocument();
  expect(screen.getByText("Tracking time unavailable")).toBeInTheDocument();
});
it("shows incomplete trip reasons once without inventing zero exposure", () => {
  const report = reportFixture();
  report.measurement_result!.metrics.forEach((m) => {
    m.completeness = {
      ...m.completeness,
      covered_trip_count: 2,
      insufficient_data_trip_count: 1,
      excluded_trip_count: 1,
      in_progress_trip_count: 2,
      complete: false,
    };
  });
  render(<MeasurementAuthorityPanel authority={validateMeasurementAuthority(report)} />);
  expect(screen.getAllByText(/Based on 2 of 4 completed trips/)).toHaveLength(1);
  expect(
    screen.getByText(/1 with too little data · 1 excluded · 2 still in progress/),
  ).toBeInTheDocument();
});

it.each([
  [null, "—"],
  ["0", "0.00 / 100"],
  ["invalid", "—"],
])("shows a truthful activity score for %s", (value, expected) => {
  render(
    <MeasurementAuthorityPanel
      authority={validateMeasurementAuthority(reportFixture())}
      activityScore={value}
    />,
  );
  expect(screen.getByText("Campaign activity score").parentElement).toHaveTextContent(expected);
});
