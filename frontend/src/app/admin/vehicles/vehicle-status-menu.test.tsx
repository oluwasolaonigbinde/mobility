import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, it, vi } from "vitest";
import { VehicleStatusMenu } from "./vehicle-status-menu";

const update = vi.hoisted(() => vi.fn());
vi.mock("../fleet-actions", () => ({ updateVehicleStatusAction: update }));

beforeEach(() => {
  update.mockReset();
  update.mockResolvedValue({});
});

it("names the vehicle in an on-page suspension confirmation", async () => {
  const user = userEvent.setup();
  render(<VehicleStatusMenu vehicleId="vehicle-1" vehicleLabel="ABC 123 XY" status="active" />);

  await user.click(screen.getByRole("button", { name: "Suspend" }));

  expect(update).not.toHaveBeenCalled();
  expect(screen.getByRole("alertdialog")).toHaveTextContent("ABC 123 XY");
  await user.click(screen.getByRole("button", { name: "Keep car active" }));
  expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
});

it("confirms a suspension once and surfaces a refusal", async () => {
  update.mockResolvedValue({ error: "Vehicle status changed elsewhere" });
  const user = userEvent.setup();
  render(<VehicleStatusMenu vehicleId="vehicle-1" vehicleLabel="ABC 123 XY" status="active" />);

  await user.click(screen.getByRole("button", { name: "Suspend" }));
  await user.click(screen.getByRole("button", { name: "Confirm suspension" }));

  await waitFor(() =>
    expect(update).toHaveBeenCalledWith({ vehicleId: "vehicle-1", status: "suspended" }),
  );
  expect(update).toHaveBeenCalledOnce();
  expect(await screen.findByRole("alert")).toHaveTextContent("Vehicle status changed elsewhere");
  expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
});

it.each(["pending", "suspended", "inactive"] as const)(
  "blocks activation or Restore for %s with terminal evidence",
  (status) => {
    render(
      <VehicleStatusMenu
        vehicleId="car"
        vehicleLabel="ABJ-714-KM"
        status={status}
        currentEvidenceStatus="expired"
      />,
    );
    const button = screen.getByRole("button", {
      name: status === "pending" ? "Approve" : "Restore",
    });
    expect(button).toBeDisabled();
    expect(button).toHaveAttribute(
      "title",
      "This car needs a fresh document submission and approval before it can be made active.",
    );
  },
);
it.each([undefined, "approved"])("allows Restore with evidence %s", (currentEvidenceStatus) => {
  render(
    <VehicleStatusMenu
      vehicleId="car"
      vehicleLabel="ABJ-TEST"
      status="suspended"
      currentEvidenceStatus={currentEvidenceStatus}
    />,
  );
  expect(screen.getByRole("button", { name: "Restore" })).toBeEnabled();
});
