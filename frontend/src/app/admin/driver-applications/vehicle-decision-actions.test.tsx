import { render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";

vi.mock("./actions", () => ({
  reviewVehicleAction: vi.fn(),
  reviewVehicleEvidenceAction: vi.fn(),
}));

import { VehicleDecisionActions } from "./vehicle-decision-actions";

it("marks approval expiry as required while a vehicle awaits review", () => {
  render(
    <VehicleDecisionActions
      applicationId="application-1"
      vehicleId="vehicle-1"
      submissionId="submission-1"
      documentFileIds={{}}
      status="pending_review"
    />,
  );

  expect(screen.getByLabelText("Approval expiry")).toBeRequired();
});
