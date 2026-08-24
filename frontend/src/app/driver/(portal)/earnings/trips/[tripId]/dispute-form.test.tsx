import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { DisputeForm } from "./dispute-form";

const actionMock = vi.hoisted(() => vi.fn());

vi.mock("./actions", () => ({ submitFraudDisputeAction: actionMock }));

describe("DisputeForm", () => {
  beforeEach(() => {
    actionMock.mockReset();
    actionMock.mockResolvedValue({});
  });

  it("requires a bounded message and submits once", async () => {
    const user = userEvent.setup();
    render(<DisputeForm flagId="flag-id" tripId="trip-id" />);

    const message = screen.getByLabelText("Dispute message");
    expect(message).toBeRequired();
    expect(message).toHaveAttribute("maxlength", "2000");
    await user.click(screen.getByRole("button", { name: "Submit dispute" }));
    expect(actionMock).not.toHaveBeenCalled();

    await user.type(message, "Please review the signal interruption.");
    await user.click(screen.getByRole("button", { name: "Submit dispute" }));
    expect(actionMock).toHaveBeenCalledTimes(1);
  });

  it("disables repeat submission while pending", async () => {
    let resolveAction!: (value: object) => void;
    actionMock.mockReturnValue(new Promise((resolve) => (resolveAction = resolve)));
    const user = userEvent.setup();
    render(<DisputeForm flagId="flag-id" tripId="trip-id" />);

    await user.type(screen.getByLabelText("Dispute message"), "Please review this trip.");
    await user.click(screen.getByRole("button", { name: "Submit dispute" }));
    expect(screen.getByRole("button", { name: "Submitting…" })).toBeDisabled();

    await act(async () => resolveAction({ done: "Submitted" }));
    expect(await screen.findByText("✓ Submitted")).toBeInTheDocument();
  });
});
