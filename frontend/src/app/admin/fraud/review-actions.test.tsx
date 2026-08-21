import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ReviewActions } from "./review-actions";

const reviewActionMock = vi.hoisted(() => vi.fn());

vi.mock("./actions", () => ({
  reviewFraudFlagAction: reviewActionMock,
}));

const FLAG_ID = "00000000-0000-4000-8000-00000000000a";

describe("ReviewActions", () => {
  beforeEach(() => {
    reviewActionMock.mockReset();
    reviewActionMock.mockResolvedValue({});
  });

  it("offers only acknowledgement for an open flag", () => {
    render(<ReviewActions flagId={FLAG_ID} status="open" />);

    expect(screen.getByRole("button", { name: "Acknowledge" })).toBeEnabled();
    expect(screen.queryByLabelText("Review note")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Confirm fraud" })).not.toBeInTheDocument();
  });

  it("requires a note before an acknowledged flag can be resolved", async () => {
    const user = userEvent.setup();
    render(<ReviewActions flagId={FLAG_ID} status="acknowledged" />);

    const note = screen.getByLabelText("Review note");
    expect(note).toBeRequired();
    expect(note).toHaveAttribute("maxlength", "2000");

    await user.click(screen.getByRole("button", { name: "Dismiss flag" }));
    expect(reviewActionMock).not.toHaveBeenCalled();

    await user.type(note, "Route evidence was not persuasive.");
    await user.click(screen.getByRole("button", { name: "Dismiss flag" }));
    expect(reviewActionMock).toHaveBeenCalledTimes(1);
  });

  it("makes the post-release reversal consequence explicit", () => {
    render(<ReviewActions flagId={FLAG_ID} status="acknowledged" reversalRecommended={true} />);

    expect(
      screen.getByRole("button", { name: "Confirm fraud & reverse released earnings" }),
    ).toBeEnabled();
  });

  it.each(["confirmed", "dismissed"] as const)("renders %s as terminal", (status) => {
    render(<ReviewActions flagId={FLAG_ID} status={status} />);

    expect(screen.queryByRole("button")).not.toBeInTheDocument();
    expect(screen.getByText(/review is final|hold removed/i)).toBeInTheDocument();
  });

  it("shows when confirmed fraud already reversed released earnings", () => {
    render(<ReviewActions flagId={FLAG_ID} status="confirmed" reversalRecorded={true} />);

    expect(screen.getByText(/released earnings were reversed/i)).toBeInTheDocument();
  });

  it("disables the control and gives pending feedback while acknowledging", async () => {
    let resolveAction!: (value: object) => void;
    reviewActionMock.mockReturnValue(
      new Promise((resolve) => {
        resolveAction = resolve;
      }),
    );
    const user = userEvent.setup();
    render(<ReviewActions flagId={FLAG_ID} status="open" />);

    await user.click(screen.getByRole("button", { name: "Acknowledge" }));
    expect(screen.getByRole("button", { name: "Acknowledging…" })).toBeDisabled();

    await act(async () => resolveAction({ done: "Review acknowledged" }));
    expect(await screen.findByText("✓ Review acknowledged")).toBeInTheDocument();
  });

  it("surfaces the backend error", async () => {
    reviewActionMock.mockResolvedValue({ error: "This flag was already resolved." });
    const user = userEvent.setup();
    render(<ReviewActions flagId={FLAG_ID} status="open" />);

    await user.click(screen.getByRole("button", { name: "Acknowledge" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("This flag was already resolved.");
  });
});
