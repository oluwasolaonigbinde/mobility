import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ReviewActions } from "./review-actions";
const review = vi.hoisted(() => vi.fn());
vi.mock("./actions", () => ({ reviewFraudFlagAction: review }));
const flagId = "00000000-0000-4000-8000-00000000000a";
describe("trip review", () => {
  beforeEach(() => {
    review.mockReset();
    review.mockResolvedValue({});
  });
  it("offers a direct final decision with a required note", async () => {
    const user = userEvent.setup();
    render(<ReviewActions flagId={flagId} status="open" />);
    expect(screen.queryByRole("button", { name: "Start review" })).toBeNull();
    const note = screen.getByLabelText("Review note");
    expect(note).toBeRequired();
    await user.click(screen.getByRole("button", { name: "Clear" }));
    expect(review).not.toHaveBeenCalled();
    await user.type(note, "Evidence checked");
    await user.click(screen.getByRole("button", { name: "Clear" }));
    expect(review).toHaveBeenCalledTimes(1);
  });
  it("explains that confirmation keeps pay held and correction is separate", () => {
    render(<ReviewActions flagId={flagId} status="open" />);
    expect(screen.getByRole("button", { name: "Confirm problem" })).toHaveAccessibleDescription(
      "Keeps this trip's held pay held. Record any money correction separately with a reason.",
    );
  });
  it.each(["confirmed", "dismissed"] as const)("%s is final", (status) => {
    render(<ReviewActions flagId={flagId} status={status} />);
    expect(screen.queryByRole("button")).toBeNull();
    expect(screen.getByText(/review is final/)).toBeInTheDocument();
  });
  it("disables both decisions while confirmation is pending", async () => {
    let complete!: (value: object) => void;
    review.mockReturnValue(
      new Promise((resolve) => {
        complete = resolve;
      }),
    );
    const user = userEvent.setup();
    render(<ReviewActions flagId={flagId} status="open" />);
    await user.type(screen.getByLabelText("Review note"), "Evidence checked");
    await user.click(screen.getByRole("button", { name: "Confirm problem" }));
    expect(screen.getByRole("button", { name: "Clear" })).toBeDisabled();
    await act(async () => complete({ done: "Decision recorded" }));
    expect(await screen.findByText(/Decision recorded/)).toBeInTheDocument();
  });
  it("shows a refusal and keeps retry available", async () => {
    review.mockResolvedValue({ error: "This flag was already resolved." });
    const user = userEvent.setup();
    render(<ReviewActions flagId={flagId} status="open" />);
    await user.type(screen.getByLabelText("Review note"), "Evidence checked");
    await user.click(screen.getByRole("button", { name: "Confirm problem" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("already resolved");
    expect(screen.getByRole("button", { name: "Clear" })).toBeEnabled();
  });
});
