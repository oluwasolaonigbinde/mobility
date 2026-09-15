import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, it, vi } from "vitest";
const update = vi.hoisted(() => vi.fn());
vi.mock("./actions", () => ({ updateUserStatusAction: update }));
import { UserStatusMenu } from "./user-status-menu";

beforeEach(() => {
  update.mockReset();
  update.mockResolvedValue({});
});

it("requires a masked password to activate an administrator and clears it after submission", async () => {
  const user = userEvent.setup();
  render(<UserStatusMenu userId="target" userLabel="Ada Admin" role="admin" status="invited" />);
  await user.click(screen.getByRole("button", { name: "Reactivate" }));
  expect(update).not.toHaveBeenCalled();
  const proof = screen.getByLabelText("Your current password");
  expect(proof).toHaveAttribute("type", "password");
  expect(proof).toBeRequired();
  await user.type(proof, "acting-admin-password");
  await user.click(screen.getByRole("button", { name: "Confirm reactivation" }));
  expect(update).toHaveBeenCalledWith({
    userId: "target",
    status: "active",
    current_password: "acting-admin-password",
  });
  expect(screen.queryByLabelText("Your current password")).not.toBeInTheDocument();
});

it("keeps ordinary driver reactivation free of elevation proof", async () => {
  const user = userEvent.setup();
  render(
    <UserStatusMenu userId="driver" userLabel="Tunde Driver" role="driver" status="suspended" />,
  );
  await user.click(screen.getByRole("button", { name: "Reactivate" }));
  expect(update).toHaveBeenCalledWith({ userId: "driver", status: "active" });
});

it("names the account in an on-page suspension confirmation", async () => {
  const user = userEvent.setup();
  render(<UserStatusMenu userId="driver" userLabel="Tunde Driver" role="driver" status="active" />);

  await user.click(screen.getByRole("button", { name: "Suspend" }));

  expect(update).not.toHaveBeenCalled();
  expect(screen.getByRole("alertdialog")).toHaveTextContent("Tunde Driver");
  await user.click(screen.getByRole("button", { name: "Keep account active" }));
  expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
});
