import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, it, vi } from "vitest";
import { CancelAssignmentButton } from "./cancel-button";

const cancel = vi.hoisted(() => vi.fn());
vi.mock("./actions", () => ({ cancelAssignmentAction: cancel }));

beforeEach(() => {
  cancel.mockReset();
  cancel.mockResolvedValue({});
});

it("collects the permanent reason in a named on-page confirmation", async () => {
  const user = userEvent.setup();
  render(
    <CancelAssignmentButton
      assignmentId="assignment-1"
      assignmentLabel="Abuja Airport launch for Tunde Driver"
    />,
  );

  await user.click(screen.getByRole("button", { name: "Cancel" }));
  expect(screen.getByRole("alertdialog")).toHaveTextContent(
    "Abuja Airport launch for Tunde Driver",
  );
  await user.type(screen.getByLabelText("Cancellation reason"), "Vehicle unavailable");
  await user.click(screen.getByRole("button", { name: "Confirm cancellation" }));

  expect(cancel).toHaveBeenCalledWith("assignment-1", "Vehicle unavailable");
});
