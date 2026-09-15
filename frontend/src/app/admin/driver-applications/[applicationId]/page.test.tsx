import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  get: vi.fn(),
  person: vi.fn(),
  vehicle: vi.fn(),
  accountSetup: vi.fn(),
}));
vi.mock("@/lib/api/client", () => ({ createApiClient: () => ({ GET: mocks.get }) }));
vi.mock("@/lib/auth/session", () => ({ getSessionToken: async () => "token" }));
vi.mock("../person-payee-decision-actions", () => ({
  PersonPayeeDecisionActions: (props: Record<string, unknown>) => {
    mocks.person(props);
    return <div>Person decision controls</div>;
  },
}));
vi.mock("../vehicle-decision-actions", () => ({
  VehicleDecisionActions: (props: Record<string, unknown>) => {
    mocks.vehicle(props);
    return <div>Vehicle decision controls</div>;
  },
}));
vi.mock("../account-setup-action", () => ({
  AccountSetupAction: (props: Record<string, unknown>) => {
    mocks.accountSetup(props);
    return <div>Account setup controls</div>;
  },
}));

import ApplicationReview from "./page";

const application = {
  id: "app-1",
  user_id: "user-1",
  full_name: "Ada Applicant",
  email: "ada@example.com",
  status: "pending_review",
  person_payee: {
    status: "pending_review",
    version: 3,
    submission_id: "person-sub",
    bank_account_version_id: "bank-version",
    bank_account_verified: true,
    document_file_ids: { identity: "file-1" },
  },
  vehicle: {
    status: "pending_review",
    plate_number: "ABJ-101",
    vehicle_id: "vehicle-1",
    submission_id: "vehicle-sub",
    document_file_ids: null,
  },
};

const props = { params: Promise.resolve({ applicationId: "app-1" }) };

describe("driver application review detail", () => {
  beforeEach(() => {
    mocks.get.mockReset();
    mocks.person.mockReset();
    mocks.vehicle.mockReset();
    mocks.accountSetup.mockReset();
  });

  it("offers decisions only for current pending evidence with exact identities", async () => {
    mocks.get.mockResolvedValue({ data: application });
    render(await ApplicationReview(props));
    expect(mocks.get).toHaveBeenCalledWith("/api/v1/admin/driver-applications/{application_id}", {
      params: { path: { application_id: "app-1" } },
    });
    expect(screen.getByRole("heading", { name: "Ada Applicant" })).toBeTruthy();
    expect(screen.getByText("ada@example.com · pending review")).toBeTruthy();
    expect(screen.getByText(/pending review\s+· Version 3/)).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Vehicle · ABJ-101" })).toBeTruthy();
    expect(mocks.person).toHaveBeenCalledWith({
      applicationId: "app-1",
      submissionId: "person-sub",
      bankAccountVersionId: "bank-version",
      bankAccountVerified: true,
      documentFileIds: { identity: "file-1" },
    });
    expect(mocks.vehicle).toHaveBeenCalledWith({
      applicationId: "app-1",
      vehicleId: "vehicle-1",
      submissionId: "vehicle-sub",
      documentFileIds: {},
      status: "pending_review",
    });
    expect(screen.getByRole("link", { name: "← All applications" })).toHaveAttribute(
      "href",
      "/admin/driver-applications",
    );
  });

  it("shows terminal and missing evidence without decision controls", async () => {
    mocks.get.mockResolvedValue({
      data: {
        ...application,
        status: "rejected",
        person_payee: { ...application.person_payee, status: "rejected", version: null },
        vehicle: { ...application.vehicle, status: "rejected" },
      },
    });
    const { unmount } = render(await ApplicationReview(props));
    expect(screen.getByText("No current person/payee decision is awaiting review.")).toBeTruthy();
    expect(screen.getByText("No current vehicle decision is awaiting review.")).toBeTruthy();
    expect(mocks.person).not.toHaveBeenCalled();
    expect(mocks.vehicle).not.toHaveBeenCalled();
    unmount();

    mocks.get.mockResolvedValue({ data: { ...application, person_payee: null, vehicle: null } });
    render(await ApplicationReview(props));
    expect(screen.getAllByText("Not submitted")).toHaveLength(2);
    expect(screen.getByRole("heading", { name: "Vehicle · Not supplied" })).toBeTruthy();
  });

  it("keeps an approved vehicle reviewable but not a pending person without bank evidence", async () => {
    mocks.get.mockResolvedValue({
      data: {
        ...application,
        person_payee: { ...application.person_payee, bank_account_version_id: null },
        vehicle: { ...application.vehicle, status: "approved" },
      },
    });
    render(await ApplicationReview(props));
    expect(mocks.person).not.toHaveBeenCalled();
    expect(mocks.vehicle).toHaveBeenCalledWith(expect.objectContaining({ status: "approved" }));
  });

  it("shows unavailable when the application cannot be read", async () => {
    mocks.get.mockResolvedValue({ data: undefined });
    render(await ApplicationReview(props));
    expect(screen.getByRole("alert")).toHaveTextContent("No empty or complete result");
  });

  it("offers account setup only after the application is approved", async () => {
    mocks.get
      .mockResolvedValueOnce({ data: { ...application, status: "approved" } })
      .mockResolvedValueOnce({ data: { items: [{ id: "user-1", status: "invited" }] } });
    const { unmount } = render(await ApplicationReview(props));
    expect(screen.getByRole("heading", { name: "Driver account setup" })).toBeTruthy();
    expect(mocks.accountSetup).toHaveBeenCalledWith({
      applicationId: "app-1",
      applicantName: "Ada Applicant",
    });
    unmount();

    mocks.accountSetup.mockClear();
    mocks.get.mockResolvedValue({ data: application });
    render(await ApplicationReview(props));
    expect(mocks.accountSetup).not.toHaveBeenCalled();
  });

  it("does not offer another setup action once the approved applicant is active", async () => {
    mocks.get
      .mockResolvedValueOnce({ data: { ...application, status: "approved" } })
      .mockResolvedValueOnce({ data: { items: [{ id: "user-1", status: "active" }] } });

    render(await ApplicationReview(props));

    expect(mocks.accountSetup).not.toHaveBeenCalled();
    expect(
      screen.getByText(
        "Account setup is already complete or is no longer available for this applicant.",
      ),
    ).toBeTruthy();
  });
});
