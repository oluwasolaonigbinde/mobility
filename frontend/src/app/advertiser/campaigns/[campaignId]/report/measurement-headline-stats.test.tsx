import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { MeasurementHeadlineStats } from "./measurement-headline-stats";

describe("MeasurementHeadlineStats", () => {
  it("keeps exposure score, impression estimates, modelled contacts and ROI distinct", () => {
    render(
      <MeasurementHeadlineStats
        exposureScore={{
          formulaVersion: "exposure_v1",
          formulaFingerprint: "a".repeat(64),
          inputFingerprint: "b".repeat(64),
          status: "scored",
          score: "84.00",
          routeCount: 1,
          missingRouteCount: 0,
          uncertainty:
            "Synthetic uncalibrated operational index; not an impression estimate, audience count, confidence interval, attribution result or ROI.",
        }}
        modelledPotentialContacts="500.00"
        modelDiagnostic="0.85"
        completeness={{
          coveredTripCount: 1,
          denominatorTripCount: 1,
          insufficientDataTripCount: 0,
          excludedTripCount: 0,
          complete: true,
          suppressed: false,
        }}
      />,
    );

    expect(screen.getByText("Campaign activity score")).toBeInTheDocument();
    expect(screen.getByText(/named “Exposure score” in downloads/i)).toBeInTheDocument();
    expect(screen.getByText("84.00 / 100")).toBeInTheDocument();
    expect(screen.getByText("Estimated ad exposure")).toBeInTheDocument();
    expect(screen.getByText(/not a count of people or measured views/i)).toBeInTheDocument();
    expect(screen.getByText(/not a statistical confidence level/i)).toBeInTheDocument();
    expect(
      screen.queryByText(/^(exposure score|modelled potential contacts|model diagnostic)$/i),
    ).not.toBeInTheDocument();
    expect(screen.getByText("500")).toBeInTheDocument();
    expect(screen.getByText(/not an impression estimate/i)).toBeInTheDocument();
    expect(
      screen.getByText(/not yet calibrated or approved as a live measurement method/i),
    ).toBeInTheDocument();
    expect(screen.getByText(/1 of 1 completed trips included/i)).toBeInTheDocument();
    expect(screen.queryByText(/ROI/i)).not.toBeInTheDocument();
    for (const summary of screen.getAllByText(/technical reference/i)) {
      expect(summary.closest("details")).not.toHaveAttribute("open");
    }
  });

  it("omits the headline total when the frozen run suppressed it", () => {
    render(
      <MeasurementHeadlineStats
        exposureScore={null}
        modelledPotentialContacts={null}
        modelDiagnostic="0.40"
        completeness={{
          coveredTripCount: 0,
          denominatorTripCount: 3,
          insufficientDataTripCount: 2,
          excludedTripCount: 1,
          complete: false,
          suppressed: true,
        }}
      />,
    );

    expect(screen.getByText("Omitted - insufficient frozen evidence")).toBeInTheDocument();
    expect(screen.queryByText("0")).not.toBeInTheDocument();
    expect(screen.getByText(/total not shown rather than counted as zero/i)).toBeInTheDocument();
    expect(screen.getByText(/2 with too little data/i)).toBeInTheDocument();
    expect(screen.getByText(/1 excluded/i)).toBeInTheDocument();
  });
});
