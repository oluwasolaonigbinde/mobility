import { act, fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, it, vi } from "vitest";
const submit = vi.hoisted(() => vi.fn());
vi.mock("./cancellation-request-actions", () => ({ requestCampaignCancellation: submit }));
import { CampaignCancellationPanel } from "./campaign-cancellation-panel";
beforeEach(() => {
  vi.resetAllMocks();
});
it("sends a reason and only then confirms that the campaign continues", async () => {
  submit.mockResolvedValue({ threadId: "thread" });
  const user = userEvent.setup();
  const { container, rerender } = render(
    <CampaignCancellationPanel campaignId="campaign" campaignName="Wuse lunch rush" />,
  );
  expect(container).not.toHaveTextContent(/cancellation requested|complaint/i);
  await user.type(screen.getByRole("textbox"), " Our opening date changed. ");
  await user.click(screen.getByRole("button", { name: "Ask Terrax to cancel" }));
  expect(submit).toHaveBeenCalledWith("campaign", "Our opening date changed.", expect.any(String));
  expect(await screen.findByRole("status")).toHaveTextContent(
    "Request sent. Your campaign continues until Terrax confirms.",
  );
  expect(screen.getByRole("link", { name: "View cancellation request" })).toHaveAttribute(
    "href",
    "/advertiser/help/thread",
  );
  expect(container).not.toHaveTextContent(/campaign cancelled|complaint/i);
  // The refreshed page passes the new request back as pending; the send stays confirmed.
  rerender(
    <CampaignCancellationPanel
      campaignId="campaign"
      campaignName="Wuse lunch rush"
      pendingThreadId="thread"
    />,
  );
  expect(screen.getByRole("status")).toHaveTextContent(
    "Request sent. Your campaign continues until Terrax confirms.",
  );
});
it("shows a request already sent instead of the form", () => {
  render(
    <CampaignCancellationPanel
      campaignId="campaign"
      campaignName="Campaign"
      pendingThreadId="earlier"
    />,
  );
  expect(screen.getByRole("status")).toHaveTextContent(
    "Cancellation requested. Your campaign continues until Terrax confirms.",
  );
  expect(screen.getByRole("link", { name: "View cancellation request" })).toHaveAttribute(
    "href",
    "/advertiser/help/earlier",
  );
  expect(screen.queryByRole("textbox")).toBeNull();
});
it("validates a trimmed short reason without dispatching", async () => {
  const user = userEvent.setup();
  const { container } = render(
    <CampaignCancellationPanel campaignId="campaign" campaignName="Campaign" />,
  );
  const reason = screen.getByRole("textbox");
  expect(reason).toBeRequired();
  expect(reason).toHaveAttribute("maxlength", "2000");
  await user.type(reason, "   ");
  await user.tab();
  fireEvent.submit(container.querySelector("form")!);
  expect(screen.getByRole("alert")).toHaveTextContent("Please add a short reason.");
  expect(submit).not.toHaveBeenCalled();
});
it("keeps the same request ID on retry and never simulates success on failure", async () => {
  submit.mockResolvedValue({ error: "Request not confirmed" });
  const user = userEvent.setup();
  render(<CampaignCancellationPanel campaignId="campaign" campaignName="Campaign" />);
  await user.type(screen.getByRole("textbox"), "Reason");
  await user.click(screen.getByRole("button", { name: "Ask Terrax to cancel" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Request not confirmed");
  expect(screen.queryByRole("status")).toBeNull();
  await user.click(screen.getByRole("button", { name: "Ask Terrax to cancel" }));
  expect(submit.mock.calls[1]![2]).toBe(submit.mock.calls[0]![2]);
  await user.type(screen.getByRole("textbox"), " changed");
  await user.click(screen.getByRole("button", { name: "Ask Terrax to cancel" }));
  expect(submit.mock.calls[2]![2]).not.toBe(submit.mock.calls[0]![2]);
});
it("suppresses double submission while the request is pending", async () => {
  let finish!: (value: { error: string }) => void;
  submit.mockImplementation(
    () =>
      new Promise((resolve) => {
        finish = resolve;
      }),
  );
  const user = userEvent.setup();
  const { container } = render(
    <CampaignCancellationPanel campaignId="campaign" campaignName="Campaign" />,
  );
  await user.type(screen.getByRole("textbox"), "Reason");
  fireEvent.submit(container.querySelector("form")!);
  fireEvent.submit(container.querySelector("form")!);
  expect(submit).toHaveBeenCalledTimes(1);
  expect(screen.getByRole("button", { name: "Sending…" })).toBeDisabled();
  await act(async () => finish({ error: "Not confirmed" }));
});
