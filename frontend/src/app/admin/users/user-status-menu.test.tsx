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
  render(<UserStatusMenu userId="target" role="admin" status="invited" />);
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
  render(<UserStatusMenu userId="driver" role="driver" status="suspended" />);
  await user.click(screen.getByRole("button", { name: "Reactivate" }));
  expect(update).toHaveBeenCalledWith({ userId: "driver", status: "active" });
});
