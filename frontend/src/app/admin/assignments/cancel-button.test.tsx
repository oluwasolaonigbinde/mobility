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

it("renders a cancellation failure once in one live alert", async () => {
  cancel.mockResolvedValue({ error: "Cancellation service unavailable." });
  const user = userEvent.setup();
  render(
    <CancelAssignmentButton
      assignmentId="assignment-1"
      assignmentLabel="Abuja Airport launch for Tunde Driver"
    />,
  );

  await user.click(screen.getByRole("button", { name: "Cancel" }));
  await user.type(screen.getByLabelText("Cancellation reason"), "Vehicle unavailable");
  await user.click(screen.getByRole("button", { name: "Confirm cancellation" }));

  expect(await screen.findByRole("alert")).toHaveTextContent("Cancellation service unavailable.");
  expect(screen.getAllByText("Cancellation service unavailable.")).toHaveLength(1);
});
