import { fireEvent, render, screen, within } from "@testing-library/react";
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
function openReviews() {
  for (const field of screen.getAllByLabelText("Review purpose")) {
    const select = field as HTMLSelectElement;
    const panel = within(select.closest("div")!);
    fireEvent.change(select, { target: { value: select.options[1]!.value } });
    fireEvent.click(panel.getByRole("checkbox"));
    fireEvent.click(panel.getByRole("button", { name: "Confirm and open protected review" }));
  }
}
it("uses clear identity document labels behind the existing protected-review confirmation", () => {
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
  expect(screen.queryByRole("button", { name: "Review driving licence" })).toBeNull();
  openReviews();
  expect(screen.getByRole("button", { name: "Review driving licence" })).toBeVisible();
  expect(screen.getByRole("button", { name: "Review signed agreement" })).toBeVisible();
  expect(screen.getByRole("button", { name: "Review driver photo" })).toBeVisible();
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
  openReviews();
  expect(screen.getByRole("button", { name: "Review car registration" })).toBeVisible();
  expect(screen.getByRole("button", { name: "Review car insurance" })).toBeVisible();
  expect(screen.getByRole("button", { name: "Review car photo" })).toBeVisible();
  expect(screen.getByRole("button", { name: "Review document" })).toBeVisible();
  expect(screen.queryByText(/private wire key|private_wire_key/)).toBeNull();
});
