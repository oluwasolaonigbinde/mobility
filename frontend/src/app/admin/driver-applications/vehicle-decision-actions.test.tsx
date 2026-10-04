import { act, fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({ read: vi.fn(), decide: vi.fn() }));
vi.mock("./actions", () => ({
  reviewVehicleAction: mocks.decide,
  reviewVehicleEvidenceAction: mocks.read,
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

const props = {
  applicationId: "application-1",
  vehicleId: "vehicle-1",
  submissionId: "submission-1",
  documentFileIds: {
    registration: "registration-1",
    insurance: "insurance-1",
    vehicle_photo: "photo-1",
  },
  status: "pending_review",
};
beforeEach(() => {
  vi.clearAllMocks();
  mocks.read.mockResolvedValue({ downloadUrl: "https://example.invalid/current" });
});
it.each([
  ["car registration", "registration-1"],
  ["car insurance", "insurance-1"],
  ["car photo", "photo-1"],
])("directly reads the current %s once per View", async (name, fileId) => {
  const user = userEvent.setup();
  render(<VehicleDecisionActions {...props} />);
  expect(mocks.read).not.toHaveBeenCalled();
  const row = within(screen.getByRole("region", { name }));
  expect(row.queryByRole("checkbox")).toBeNull();
  expect(row.getByText("Purpose: Vehicle review")).toBeInTheDocument();
  await user.click(row.getByRole("button", { name: "View" }));
  expect(await row.findByRole("link")).toHaveAttribute("href", "https://example.invalid/current");
  expect(mocks.read).toHaveBeenCalledTimes(1);
  const payload = mocks.read.mock.calls[0]![1] as FormData;
  expect(payload.get("file_id")).toBe(fileId);
  expect(payload.get("submission_id")).toBe("submission-1");
});
it("hides one car document independently and logs its reopened read", async () => {
  const user = userEvent.setup();
  render(<VehicleDecisionActions {...props} />);
  const registration = within(screen.getByRole("region", { name: "car registration" }));
  const insurance = within(screen.getByRole("region", { name: "car insurance" }));
  await user.click(registration.getByRole("button", { name: "View" }));
  await user.click(insurance.getByRole("button", { name: "View" }));
  await user.click(registration.getByRole("button", { name: "Hide" }));
  expect(registration.queryByRole("link")).toBeNull();
  expect(insurance.getByRole("link")).toBeInTheDocument();
  await user.click(registration.getByRole("button", { name: "View" }));
  expect(await registration.findByRole("link")).toBeInTheDocument();
  expect(mocks.read).toHaveBeenCalledTimes(3);
});
it("clears failed reads on hide and retries with a fresh audited read", async () => {
  const user = userEvent.setup();
  mocks.read.mockResolvedValueOnce({ error: "Evidence unavailable" });
  render(<VehicleDecisionActions {...props} />);
  const row = within(screen.getByRole("region", { name: "car registration" }));
  await user.click(row.getByRole("button", { name: "View" }));
  await row.findByText("Evidence unavailable");
  expect(row.queryByRole("link")).toBeNull();
  await user.click(row.getByRole("button", { name: "Hide" }));
  expect(row.queryByText("Evidence unavailable")).toBeNull();
  await user.click(row.getByRole("button", { name: "View" }));
  await row.findByRole("link");
  expect(mocks.read).toHaveBeenCalledTimes(2);
});
it.each(["manual", "file", "submission", "vehicle"])(
  "discards an older response after %s reset and a newer read",
  async (reset) => {
    const user = userEvent.setup();
    let oldResolve!: (value: { downloadUrl: string }) => void;
    let newResolve!: (value: { downloadUrl: string }) => void;
    mocks.read
      .mockImplementationOnce(
        () =>
          new Promise((resolve) => {
            oldResolve = resolve;
          }),
      )
      .mockImplementationOnce(
        () =>
          new Promise((resolve) => {
            newResolve = resolve;
          }),
      );
    const { rerender } = render(<VehicleDecisionActions {...props} />);
    let row = within(screen.getByRole("region", { name: "car registration" }));
    await user.click(row.getByRole("button", { name: "View" }));
    expect(row.getByRole("button", { name: "Opening…" })).toBeDisabled();
    if (reset === "manual") await user.click(row.getByRole("button", { name: "Hide" }));
    else
      rerender(
        <VehicleDecisionActions
          {...props}
          submissionId={reset === "submission" ? "submission-2" : props.submissionId}
          vehicleId={reset === "vehicle" ? "vehicle-2" : props.vehicleId}
          documentFileIds={
            reset === "file" ? { registration: "registration-2" } : props.documentFileIds
          }
        />,
      );
    row = within(screen.getByRole("region", { name: "car registration" }));
    expect(row.getByRole("button", { name: "View" })).toBeEnabled();
    expect(row.queryByRole("link")).toBeNull();
    await user.click(row.getByRole("button", { name: "View" }));
    await act(async () => newResolve({ downloadUrl: "https://example.invalid/new" }));
    await act(async () => oldResolve({ downloadUrl: "https://example.invalid/old" }));
    expect(await row.findByRole("link")).toHaveAttribute("href", "https://example.invalid/new");
    const payload = mocks.read.mock.calls[1]![1] as FormData;
    expect(payload.get("submission_id")).toBe(
      reset === "submission" ? "submission-2" : "submission-1",
    );
    expect(payload.get("file_id")).toBe(reset === "file" ? "registration-2" : "registration-1");
  },
);
it.each(["timeout", "pagehide", "visibilitychange"])(
  "clears actual car read state on %s",
  async (event) => {
    vi.useFakeTimers();
    try {
      render(<VehicleDecisionActions {...props} />);
      const row = within(screen.getByRole("region", { name: "car registration" }));
      await act(async () => fireEvent.click(row.getByRole("button", { name: "View" })));
      expect(row.getByRole("link")).toBeInTheDocument();
      if (event === "timeout") act(() => vi.advanceTimersByTime(60000));
      else if (event === "pagehide") fireEvent(window, new Event("pagehide"));
      else {
        Object.defineProperty(document, "visibilityState", { configurable: true, value: "hidden" });
        fireEvent(document, new Event("visibilitychange"));
        Object.defineProperty(document, "visibilityState", {
          configurable: true,
          value: "visible",
        });
      }
      expect(row.queryByRole("link")).toBeNull();
      expect(row.getByRole("button", { name: "View" })).toBeEnabled();
    } finally {
      vi.useRealTimers();
    }
  },
);
it("does not read empty collections and preserves the approved-car decision branch", () => {
  const { rerender } = render(<VehicleDecisionActions {...props} documentFileIds={{}} />);
  expect(screen.queryByRole("button", { name: "View" })).toBeNull();
  expect(mocks.read).not.toHaveBeenCalled();
  expect(screen.getByLabelText("Approval expiry")).toBeRequired();
  for (const name of [
    "Owner matches",
    "Car details match",
    "Roadworthy",
    "Pilot car eligible",
    "Documents readable",
  ])
    expect(screen.getByLabelText(name)).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Reject" })).toHaveAttribute("formnovalidate");
  rerender(<VehicleDecisionActions {...props} status="approved" />);
  expect(screen.getByText("Current approved car")).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "View" })).toBeNull();
  expect(mocks.read).not.toHaveBeenCalled();
  expect(screen.getByRole("button", { name: "Mark expired" })).toBeEnabled();
});

it("times each vehicle document independently", async () => {
  vi.useFakeTimers();
  try {
    render(<VehicleDecisionActions {...props} />);
    const registration = within(screen.getByRole("region", { name: "car registration" }));
    const insurance = within(screen.getByRole("region", { name: "car insurance" }));
    await act(async () => fireEvent.click(registration.getByRole("button", { name: "View" })));
    act(() => vi.advanceTimersByTime(45000));
    await act(async () => fireEvent.click(insurance.getByRole("button", { name: "View" })));
    act(() => vi.advanceTimersByTime(15000));
    expect(registration.queryByRole("link")).toBeNull();
    expect(insurance.getByRole("link")).toBeInTheDocument();
    act(() => vi.advanceTimersByTime(45000));
    expect(insurance.queryByRole("link")).toBeNull();
  } finally {
    vi.useRealTimers();
  }
});
