import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  AllocateDebtForm,
  BatchActions,
  CreateBatchForm,
  MaskedDestination,
  PollLineAction,
} from "./batch-forms";
import type { EligiblePayment } from "./operation-types";

const calls = vi.hoisted(() => ({
  reserve: vi.fn(),
  preview: vi.fn(),
  mask: vi.fn(),
  transition: vi.fn(),
  allocate: vi.fn(),
  poll: vi.fn(),
}));
vi.mock("./actions", () => ({
  createAndReserveBatchAction: calls.reserve,
  previewSelectionAction: calls.preview,
  maskedDestinationAction: calls.mask,
  batchTransitionAction: calls.transition,
  allocateDebtAction: calls.allocate,
  pollLineAction: calls.poll,
}));

const entry: EligiblePayment = {
  ledger_entry_id: "22222222-2222-4222-8222-222222222222",
  driver_profile_id: "33333333-3333-4333-8333-333333333333",
  driver_name: "Ada Driver",
  payee_name: "Ada Driver",
  campaign_name: "Test Campaign",
  occurred_at: "2026-09-14T10:00:00Z",
  amount: "100.07",
  currency: "NGN",
  debt_deducted: "0.00",
  carry_forward_debt: "0.00",
  destination_verified: true,
  bank_account_version_id: null,
  eligible: true,
  ineligibility_reasons: [],
};

async function clickWhenEnabled(
  user: { click: (element: Element) => Promise<void> },
  name: string | RegExp,
) {
  const button = await screen.findByRole("button", { name });
  await vi.waitFor(() => expect(button).toBeEnabled());
  await user.click(button);
}

async function checkWhenEnabled(user: { click: (element: Element) => Promise<void> }) {
  const checkbox = screen.getByRole("checkbox");
  await vi.waitFor(() => expect(checkbox).toBeEnabled());
  await user.click(checkbox);
}

describe("payout form states", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    Object.defineProperty(navigator, "locks", {
      configurable: true,
      value: { request: vi.fn(async (_key, work) => work()) },
    });
  });
  afterEach(() => vi.useRealTimers());

  it("shows debt, unverified destination and missing payee context on credit cards", () => {
    render(
      <CreateBatchForm
        entries={[
          {
            ...entry,
            payee_name: null,
            destination_verified: false,
            debt_deducted: "10.02",
            carry_forward_debt: "5.00",
            bank_account_version_id: "44444444-4444-4444-8444-444444444444",
          },
        ]}
        actorId="maker"
      />,
    );
    expect(screen.getByText(/Payee: Not configured · Destination unavailable/)).toBeTruthy();
    expect(screen.getByText(/Debt already deducted: .*10\.02/)).toBeTruthy();
    expect(screen.getByText(/Outstanding debt: .*5\.00/)).toBeTruthy();
    expect(screen.getByRole("button", { name: "Allocate debt" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Review masked destination" })).toBeTruthy();
  });

  it("states when no credits match and keeps creation disabled", () => {
    render(<CreateBatchForm entries={[]} actorId="maker" />);
    expect(screen.getByText("No available credits match these filters.")).toBeTruthy();
    expect(
      screen.getByRole("button", { name: "Create and reserve selected credits" }),
    ).toBeDisabled();
  });

  it("clears the preview when a selection is removed", async () => {
    calls.preview.mockResolvedValue({ currency: "NGN", total_amount: "100.07" });
    const user = userEvent.setup();
    render(<CreateBatchForm entries={[entry]} actorId="maker" />);
    await user.click(screen.getByRole("checkbox"));
    await clickWhenEnabled(user, "Review selected credits");
    expect(await screen.findByText(/Advisory selected total/)).toBeTruthy();
    await checkWhenEnabled(user);
    expect(screen.queryByText(/Advisory selected total/)).toBeNull();
    expect(screen.queryByRole("button", { name: "Review selected credits" })).toBeNull();
  });

  it("warns when saved recovery storage cannot be read", () => {
    localStorage.setItem("cardvert-payout-draft:maker", "{not json");
    render(<CreateBatchForm entries={[entry]} actorId="maker" />);
    expect(screen.getByRole("alert")).toHaveTextContent("Saved recovery is unavailable");
  });

  it("keeps the saved request when the reservation call itself fails", async () => {
    calls.preview.mockResolvedValue({ currency: "NGN", total_amount: "100.07" });
    calls.reserve.mockRejectedValue(new Error("network"));
    const user = userEvent.setup();
    render(<CreateBatchForm entries={[entry]} actorId="maker" />);
    await user.click(screen.getByRole("checkbox"));
    await clickWhenEnabled(user, "Review selected credits");
    await screen.findByText(/Advisory selected total/);
    await clickWhenEnabled(user, "Create and reserve selected credits");
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "recover the existing draft before trying again",
    );
    expect(localStorage.getItem("cardvert-payout-draft:maker")).not.toBeNull();
  });

  it("links the confirmed batch and clears recovery only when the operator starts again", async () => {
    calls.preview.mockResolvedValue({ currency: "NGN", total_amount: "100.07" });
    calls.reserve.mockResolvedValue({
      done: "Reservation confirmed. Open the batch to review its current status.",
      batchId: "batch-1",
    });
    const user = userEvent.setup();
    render(<CreateBatchForm entries={[entry]} actorId="maker" />);
    await user.click(screen.getByRole("checkbox"));
    await clickWhenEnabled(user, "Review selected credits");
    await screen.findByText(/Advisory selected total/);
    await clickWhenEnabled(user, "Create and reserve selected credits");
    expect(await screen.findByRole("status")).toHaveTextContent("Reservation confirmed");
    expect(screen.getByRole("link", { name: "Review this batch" })).toHaveAttribute(
      "href",
      "/admin/payouts/batches/batch-1",
    );
    await clickWhenEnabled(user, "Finish recovery");
    expect(localStorage.getItem("cardvert-payout-draft:maker")).toBeNull();
    expect(screen.queryByRole("status")).toBeNull();
    expect(screen.getByRole("checkbox")).not.toBeChecked();
  });

  it("allocates debt only after confirmation and reports the result", async () => {
    const confirm = vi.spyOn(window, "confirm").mockReturnValueOnce(false).mockReturnValue(true);
    calls.allocate.mockResolvedValue({ done: "Available credits allocated to carry-forward debt" });
    const user = userEvent.setup();
    render(<AllocateDebtForm entry={{ ...entry, carry_forward_debt: "5.00" }} />);
    await user.click(screen.getByRole("button", { name: "Allocate debt" }));
    expect(confirm).toHaveBeenCalledWith(
      "Allocate available NGN credits to Ada Driver's carry-forward debt?",
    );
    expect(calls.allocate).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: "Allocate debt" }));
    expect(await screen.findByRole("status")).toHaveTextContent("allocated to carry-forward debt");
    const sent = calls.allocate.mock.calls[0]![1] as FormData;
    expect(sent.get("driver_profile_id")).toBe(entry.driver_profile_id);
    expect(sent.get("currency")).toBe("NGN");
  });

  it("shows a debt allocation refusal", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    calls.allocate.mockResolvedValue({ error: "The allocation could not be confirmed." });
    render(<AllocateDebtForm entry={entry} />);
    await userEvent.click(screen.getByRole("button", { name: "Allocate debt" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("could not be confirmed");
  });

  it("shows a destination review error and hides a mask when the page is hidden", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    calls.mask.mockResolvedValueOnce({ error: "Administrator access is required." });
    const { unmount } = render(<MaskedDestination versionId="version" />);
    await userEvent.click(screen.getByRole("button", { name: "Review masked destination" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Administrator access is required.");
    unmount();

    calls.mask.mockResolvedValueOnce({ mask: "Bank 058 · account ending 6789" });
    render(<MaskedDestination versionId="version" />);
    await userEvent.click(screen.getByRole("button", { name: "Review masked destination" }));
    expect(await screen.findByText(/account ending 6789/)).toBeTruthy();
    Object.defineProperty(document, "hidden", { configurable: true, value: true });
    act(() => {
      document.dispatchEvent(new Event("visibilitychange"));
    });
    expect(screen.queryByText(/account ending 6789/)).toBeNull();
    Object.defineProperty(document, "hidden", { configurable: true, value: false });
  });

  it("asks before voiding a reservation and reports a refused transition", async () => {
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);
    calls.transition.mockResolvedValue({ error: "A different administrator must approve." });
    render(<BatchActions batchId="batch-1" status="reserved" />);
    await userEvent.click(screen.getByRole("button", { name: "Void reservation" }));
    expect(confirm).toHaveBeenCalledWith("Release this batch's pre-provider reservations?");
    expect(calls.transition).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole("button", { name: "Queue submission" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("different administrator");
    expect((calls.transition.mock.calls[0]![1] as FormData).get("intent")).toBe("submit");
  });

  it("reports line verification results and refusals", async () => {
    calls.poll.mockResolvedValueOnce({ done: "Verified provider result applied to this line" });
    const { unmount } = render(<PollLineAction lineId="line-1" />);
    await userEvent.click(screen.getByRole("button", { name: "Verify line" }));
    expect(await screen.findByRole("status")).toHaveTextContent("Verified provider result");
    expect((calls.poll.mock.calls[0]![1] as FormData).get("line_id")).toBe("line-1");
    unmount();

    calls.poll.mockResolvedValueOnce({ error: "Manual verification requires another admin." });
    render(<PollLineAction lineId="line-1" />);
    await userEvent.click(screen.getByRole("button", { name: "Verify line" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("another admin");
  });
});
