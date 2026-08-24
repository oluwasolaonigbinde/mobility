import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { DisputeReplyActions } from "./dispute-actions";

const actionMock = vi.hoisted(() => vi.fn());

vi.mock("./actions", () => ({ replyFraudDisputeAction: actionMock }));

describe("DisputeReplyActions", () => {
  beforeEach(() => {
    actionMock.mockReset();
    actionMock.mockResolvedValue({});
  });

  it("keeps the driver reply separate and requires bounded text", async () => {
    const user = userEvent.setup();
    render(<DisputeReplyActions disputeId="dispute-id" />);

    const reply = screen.getByLabelText("Reply to driver");
    expect(reply).toBeRequired();
    expect(reply).toHaveAttribute("maxlength", "2000");
    await user.click(screen.getByRole("button", { name: "Send reply" }));
    expect(actionMock).not.toHaveBeenCalled();

    await user.type(reply, "We reviewed the route and cleared the hold.");
    await user.click(screen.getByRole("button", { name: "Send reply" }));
    expect(actionMock).toHaveBeenCalledTimes(1);
  });
});
