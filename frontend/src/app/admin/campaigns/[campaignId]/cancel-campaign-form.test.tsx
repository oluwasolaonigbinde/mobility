import { act, fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, it, vi } from "vitest";
const cancel = vi.hoisted(() => vi.fn());
vi.mock("./cancellation-actions", () => ({ cancelWholeCampaign: cancel }));
import { CancelCampaignForm } from "./cancel-campaign-form";
beforeEach(() => {
  vi.resetAllMocks();
});
it("requires a reason and explicit confirmation before cancelling", async () => {
  cancel.mockResolvedValue({ done: "Campaign cancelled. Review billing for any settlement." });
  const user = userEvent.setup();
  render(<CancelCampaignForm campaignId="campaign" campaignName="Wuse" complaintId="thread" />);
  const reason = screen.getByRole("textbox", { name: "Reason" });
  expect(reason).toBeRequired();
  expect(reason).toHaveAttribute("maxlength", "1000");
  await user.type(reason, " Customer request ");
  await user.click(screen.getByRole("button", { name: "Cancel campaign" }));
  const dialog = screen.getByRole("alertdialog");
  expect(dialog).toHaveTextContent("Drivers are paid for valid work already done");
  expect(cancel).not.toHaveBeenCalled();
  await user.click(within(dialog).getByRole("button", { name: "Keep campaign running" }));
  expect(cancel).not.toHaveBeenCalled();
  expect(screen.queryByRole("alertdialog")).toBeNull();
  await user.click(screen.getByRole("button", { name: "Cancel campaign" }));
  await user.click(
    within(screen.getByRole("alertdialog")).getByRole("button", { name: "Cancel campaign" }),
  );
  expect(cancel).toHaveBeenCalledWith({
    campaignId: "campaign",
    complaintId: "thread",
    reason: "Customer request",
    requestId: expect.any(String),
  });
  expect(await screen.findByRole("status")).toHaveTextContent("Campaign cancelled.");
});
it("never sends whitespace-only reasons", async () => {
  const user = userEvent.setup();
  const { container } = render(<CancelCampaignForm campaignId="campaign" campaignName="Wuse" />);
  await user.type(screen.getByRole("textbox"), "   ");
  fireEvent.submit(container.querySelector("form")!);
  expect(screen.getByRole("alert")).toHaveTextContent("Add a reason");
  expect(screen.queryByRole("alertdialog")).toBeNull();
  expect(cancel).not.toHaveBeenCalled();
});
it("keeps exact retry identity after an unknown response and suppresses double clicks", async () => {
  let finish!: (state: { error: string }) => void;
  cancel
    .mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          finish = resolve;
        }),
    )
    .mockResolvedValue({ error: "Not confirmed" });
  const user = userEvent.setup();
  render(<CancelCampaignForm campaignId="campaign" campaignName="Wuse" />);
  await user.type(screen.getByRole("textbox"), "Customer request");
  await user.click(screen.getByRole("button", { name: "Cancel campaign" }));
  const confirm = within(screen.getByRole("alertdialog")).getByRole("button", {
    name: "Cancel campaign",
  });
  fireEvent.click(confirm);
  fireEvent.click(confirm);
  expect(cancel).toHaveBeenCalledTimes(1);
  await act(async () => finish({ error: "Not confirmed" }));
  expect(screen.queryByRole("status")).toBeNull();
  await user.click(
    within(screen.getByRole("alertdialog")).getByRole("button", { name: "Cancel campaign" }),
  );
  expect(cancel).toHaveBeenCalledTimes(2);
  expect(cancel.mock.calls[1]![0].requestId).toBe(cancel.mock.calls[0]![0].requestId);
});
