import { render, screen, waitFor } from "@testing-library/react";
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

it("confirms a rejection once and surfaces a refusal", async () => {
  update.mockResolvedValue({ error: "Driver status changed elsewhere" });
  const user = userEvent.setup();
  render(
    <DriverOnboardingMenu driverProfileId="driver-1" driverName="Tunde Driver" status="pending" />,
  );

  await user.click(screen.getByRole("button", { name: "Reject" }));
  await user.click(screen.getByRole("button", { name: "Confirm rejection" }));

  await waitFor(() =>
    expect(update).toHaveBeenCalledWith({ driverProfileId: "driver-1", status: "rejected" }),
  );
  expect(update).toHaveBeenCalledOnce();
  expect(await screen.findByRole("alert")).toHaveTextContent("Driver status changed elsewhere");
  expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
});

it("explains suspension separately and leaves an active driver unchanged on cancel", async () => {
  const user = userEvent.setup();
  render(
    <DriverOnboardingMenu driverProfileId="driver-1" driverName="Tunde Driver" status="active" />,
  );

  await user.click(screen.getByRole("button", { name: "Suspend" }));

  const dialog = screen.getByRole("alertdialog");
  expect(dialog).toHaveTextContent("Suspend Tunde Driver?");
  expect(dialog).toHaveTextContent("no longer be able to start campaign work");
  expect(screen.getByRole("button", { name: "Confirm suspension" })).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Keep driver active" }));
  expect(update).not.toHaveBeenCalled();
  expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
});
