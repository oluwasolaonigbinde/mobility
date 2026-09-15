import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, it, vi } from "vitest";
import { DriverOnboardingMenu } from "./onboarding-menu";

const update = vi.hoisted(() => vi.fn());
vi.mock("../fleet-actions", () => ({ updateDriverOnboardingAction: update }));

beforeEach(() => {
  update.mockReset();
  update.mockResolvedValue({});
});

it("names the driver in an on-page rejection confirmation", async () => {
  const user = userEvent.setup();
  render(
    <DriverOnboardingMenu driverProfileId="driver-1" driverName="Tunde Driver" status="pending" />,
  );

  await user.click(screen.getByRole("button", { name: "Reject" }));

  expect(update).not.toHaveBeenCalled();
  expect(screen.getByRole("alertdialog")).toHaveTextContent("Tunde Driver");
  await user.click(screen.getByRole("button", { name: "Keep pending" }));
  expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
});
