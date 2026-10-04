import { render, screen, within } from "@testing-library/react";
import { expect, it, vi } from "vitest";
vi.mock("./actions", () => ({
  reviewPersonPayeeAction: vi.fn(),
  reviewPersonPayeeEvidenceAction: vi.fn(),
  verifyPersonPayeeAccountAction: vi.fn(),
  reviewVehicleAction: vi.fn(),
  reviewVehicleEvidenceAction: vi.fn(),
}));
import { PersonPayeeDecisionActions } from "./person-payee-decision-actions";
import { VehicleDecisionActions } from "./vehicle-decision-actions";
it("uses clear identity document labels with direct audited reads", () => {
  render(
    <PersonPayeeDecisionActions
      applicationId="application"
      submissionId="submission"
      bankAccountVersionId="bank"
      bankAccountVerified
      documentFileIds={{
        driver_license: "licence",
        signed_agreement: "agreement",
        driver_photo: "photo",
      }}
    />,
  );
  for (const name of [
    "Identity (NIN)",
    "Driver’s licence",
    "Driver photo",
    "Signed agreement",
    "Bank account",
  ]) {
    const row = within(screen.getByRole("region", { name }));
    expect(
      row.getByRole("button", { name: name === "Identity (NIN)" ? "Show NIN" : "View" }),
    ).toBeEnabled();
    expect(row.queryByRole("checkbox")).toBeNull();
    expect(row.getByText(/Purpose:/)).toBeInTheDocument();
  }
});
it("uses car document labels and hides unknown internal document keys", () => {
  render(
    <VehicleDecisionActions
      applicationId="application"
      vehicleId="car"
      submissionId="submission"
      documentFileIds={{
        registration: "registration",
        insurance: "insurance",
        vehicle_photo: "photo",
        private_wire_key: "other",
      }}
      status="pending_review"
    />,
  );
  for (const name of ["car registration", "car insurance", "car photo", "document"]) {
    const row = within(screen.getByRole("region", { name }));
    expect(row.getByRole("button", { name: "View" })).toBeEnabled();
    expect(row.getByText("Purpose: Vehicle review")).toBeVisible();
    expect(row.queryByRole("checkbox")).toBeNull();
  }
  expect(screen.queryByText(/private wire key|private_wire_key/)).toBeNull();
});
