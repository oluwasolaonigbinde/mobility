import { render, screen } from "@testing-library/react";
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
  await user.click(screen.getByRole("button", { name: "Keep vehicle active" }));
  expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
});
