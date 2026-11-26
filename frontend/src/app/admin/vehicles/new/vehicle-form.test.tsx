import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";

const create = vi.hoisted(() => vi.fn());
vi.mock("../../fleet-actions", () => ({ createVehicleAction: create }));

import { VehicleForm } from "./vehicle-form";

it("sends the car type without showing a raw vehicle-type choice", async () => {
  create.mockResolvedValue({});
  const user = userEvent.setup();
  render(<VehicleForm users={[]} fixedUserId="driver-user" />);
  expect(screen.queryByLabelText("Vehicle type")).toBeNull();
  expect(screen.queryByRole("option", { name: "car" })).toBeNull();
  await user.type(screen.getByLabelText(/Plate number/), "ABC-482-KJ");
  await user.click(screen.getByRole("button", { name: "Add car" }));
  await waitFor(() => expect(create).toHaveBeenCalledOnce());
  const data = create.mock.calls[0]![1] as FormData;
  expect(data.get("vehicle_type")).toBe("car");
  expect(data.get("user_id")).toBe("driver-user");
});
