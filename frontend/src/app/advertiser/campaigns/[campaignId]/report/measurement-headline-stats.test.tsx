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
        estimatedTripCount={1}
        modelDiagnostic="0.85"
      />,
    );

    expect(screen.getByText("Exposure score")).toBeInTheDocument();
    expect(screen.getByText("84.00 / 100")).toBeInTheDocument();
    expect(screen.getByText("Modelled potential contacts")).toBeInTheDocument();
    expect(screen.getByText("500")).toBeInTheDocument();
    expect(screen.getByText(/not an impression estimate/i)).toBeInTheDocument();
    expect(screen.queryByText(/ROI/i)).not.toBeInTheDocument();
  });
});
