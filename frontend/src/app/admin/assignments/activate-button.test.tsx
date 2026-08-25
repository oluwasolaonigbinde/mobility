import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ActivateAssignmentButton } from "./activate-button";

const mocks = vi.hoisted(() => ({ activate: vi.fn() }));

vi.mock("./actions", () => ({ activateAssignmentAction: mocks.activate }));

const ASSIGNMENT_ID = "00000000-0000-4000-8000-000000000001";

describe("ActivateAssignmentButton", () => {
  beforeEach(() => {
    mocks.activate.mockReset();
  });

  it("uses the admin activation action and renders fail-closed errors", async () => {
    const user = userEvent.setup();
    mocks.activate.mockResolvedValue({ error: "Approval gates are unavailable" });
    render(<ActivateAssignmentButton assignmentId={ASSIGNMENT_ID} />);

    await user.click(screen.getByRole("button", { name: "Activate" }));

    await waitFor(() => expect(mocks.activate).toHaveBeenCalledWith(ASSIGNMENT_ID));
    expect(await screen.findByRole("alert")).toHaveTextContent("Approval gates are unavailable");
  });
});
