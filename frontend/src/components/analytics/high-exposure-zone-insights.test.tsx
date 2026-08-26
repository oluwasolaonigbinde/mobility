import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { HighExposureZoneInsights } from "./high-exposure-zone-insights";

const readyInsight = {
  state: "ready" as const,
  campaign_id: "00000000-0000-0000-0000-000000000001",
  campaign_exposure_score: "84.00",
  items: [
    {
      rank: 1,
      zone_id: "00000000-0000-0000-0000-000000000002",
      zone_name: "Central Abuja",
      modelled_potential_contacts: "120.0000",
      trip_count: 4,
    },
  ],
  provenance: {
    formula_version: "high_exposure_zone_v1" as const,
    formula_fingerprint: "a".repeat(64),
    measurement_run_id: "00000000-0000-0000-0000-000000000003",
    exposure_score_id: "00000000-0000-0000-0000-000000000004",
    exposure_formula_version: "exposure_v1",
    exposure_formula_fingerprint: "b".repeat(64),
    exposure_input_fingerprint: "c".repeat(64),
    source_segments: [
      {
        segment_id: "00000000-0000-0000-0000-000000000005",
        segment_version: 1,
        segment_snapshot_sha256: "d".repeat(64),
        reissue_of_segment_id: null,
      },
    ],
  },
  uncertainty:
    "Modelled potential contacts carry model uncertainty; exposure score is uncalibrated.",
  disclaimer:
    "Ranks zones by modelled potential contacts. Exposure score, impressions, contacts and ROI are separate measures.",
};

describe("HighExposureZoneInsights", () => {
  it("keeps ranked-zone, exposure-score, contact, impression and ROI terminology distinct", () => {
    render(<HighExposureZoneInsights insight={readyInsight} surface="report" />);

    expect(screen.getByText("High-exposure zones")).toBeInTheDocument();
    expect(screen.getByText("#1 Central Abuja")).toBeInTheDocument();
    expect(screen.getByText(/120 modelled potential contacts/i)).toBeInTheDocument();
    expect(screen.getByText(/campaign exposure score: 84\.00 \/ 100/i)).toBeInTheDocument();
    expect(screen.getByText(/impressions, contacts and ROI are separate/i)).toBeInTheDocument();
  });

  it("renders a map ranking and fails closed for suppressed output", () => {
    const { rerender } = render(<HighExposureZoneInsights insight={readyInsight} surface="map" />);
    expect(
      screen.getByRole("region", { name: "High-exposure zone map ranking" }),
    ).toBeInTheDocument();
    expect(screen.getByText("#1 Central Abuja")).toBeInTheDocument();

    rerender(
      <HighExposureZoneInsights
        surface="map"
        insight={{
          ...readyInsight,
          state: "suppressed",
          campaign_exposure_score: null,
          items: [],
          provenance: null,
          uncertainty: null,
        }}
      />,
    );
    expect(screen.getByText(/withheld by the disclosure floor/i)).toBeInTheDocument();
    expect(screen.queryByText("Central Abuja")).not.toBeInTheDocument();
    expect(screen.queryByText(/120 modelled/i)).not.toBeInTheDocument();
  });
});
