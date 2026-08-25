import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { AssignmentActions } from "./assignment-actions";

const mocks = vi.hoisted(() => ({ assignmentAction: vi.fn() }));

vi.mock("./actions", () => ({ assignmentAction: mocks.assignmentAction }));

const ASSIGNMENT_ID = "00000000-0000-4000-8000-000000000001";

describe("AssignmentActions", () => {
  beforeEach(() => {
    mocks.assignmentAction.mockReset();
    mocks.assignmentAction.mockResolvedValue({});
  });

  it("lets the driver accept or decline an offer", async () => {
    const user = userEvent.setup();
    render(<AssignmentActions assignmentId={ASSIGNMENT_ID} status="offered" />);

    await user.click(screen.getByRole("button", { name: "Accept job" }));
    await waitFor(() =>
      expect(mocks.assignmentAction).toHaveBeenCalledWith({
        assignmentId: ASSIGNMENT_ID,
        action: "accept",
      }),
    );

    await user.click(screen.getByRole("button", { name: "Decline offer" }));
    await waitFor(() =>
      expect(mocks.assignmentAction).toHaveBeenCalledWith({
        assignmentId: ASSIGNMENT_ID,
        action: "decline",
      }),
    );
  });

  it("shows accepted offers as awaiting admin activation", () => {
    render(<AssignmentActions assignmentId={ASSIGNMENT_ID} status="accepted" />);

    expect(screen.getByText("Awaiting admin activation.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /activate/i })).not.toBeInTheDocument();
  });
});
