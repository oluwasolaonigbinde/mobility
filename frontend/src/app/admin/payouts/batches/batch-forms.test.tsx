import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { BatchActions, CreateBatchForm, MaskedDestination } from "./batch-forms";

it("keeps an unsent run saved when payments are not connected", () => {
  render(<BatchActions batchId="saved" status="reserved" approved providerReady={false} />);
  expect(screen.queryByRole("button", { name: "Send payments" })).not.toBeInTheDocument();
  expect(screen.getByText("Run saved, not sent. Payments are not connected.")).toBeInTheDocument();
});
import type { EligiblePayment } from "./operation-types";

const calls = vi.hoisted(() => ({
  reserve: vi.fn(),
  preview: vi.fn(),
  mask: vi.fn(),
  transition: vi.fn(),
}));
vi.mock("./actions", () => ({
  createAndReserveBatchAction: calls.reserve,
  previewSelectionAction: calls.preview,
  maskedDestinationAction: calls.mask,
  batchTransitionAction: calls.transition,
  pollLineAction: vi.fn(),
}));
const entry: EligiblePayment = {
  ledger_entry_id: "22222222-2222-4222-8222-222222222222",
  driver_profile_id: "33333333-3333-4333-8333-333333333333",
  driver_name: "Ada Driver",
  payee_name: "Ada Driver",
  campaign_name: "Test Campaign",
  occurred_at: "2026-09-14T10:00:00Z",
  amount: "100.07",
  ledger_amount: "100.07",
  currency: "NGN",
  destination_verified: true,
  bank_account_version_id: null,
  eligible: true,
  ineligibility_reasons: [],
};

describe("payout operator forms", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.clearAllMocks();
    localStorage.clear();
    Object.defineProperty(navigator, "locks", {
      configurable: true,
      value: { request: vi.fn(async (_key, work) => work()) },
    });
    calls.preview.mockResolvedValue({ currency: "NGN", total_amount: "100.07" });
    calls.reserve.mockResolvedValue({ error: "Lost response. Retry saved request." });
  });

  it("shows reserved earnings separately from the zero available to pay", () => {
    render(
      <CreateBatchForm
        entries={[
          {
            ...entry,
            amount: "0.00",
            eligible: false,
            ineligibility_reasons: ["Already reserved or in flight"],
          },
        ]}
        actorId="maker"
      />,
    );
    expect(screen.getByText("Earnings ₦100.07")).toBeVisible();
    expect(screen.getByText("Available to pay: ₦0.00")).toBeVisible();
    expect(screen.getByRole("checkbox", { name: /100.07.*0.00/ })).toBeDisabled();
    expect(screen.getByText("Already set aside in a payment run or being sent")).toBeVisible();
  });

  it("keeps selection based on payable authority when earnings are partially settled", async () => {
    const user = userEvent.setup();
    render(<CreateBatchForm entries={[{ ...entry, amount: "25.03" }]} actorId="maker" />);
    expect(screen.getByText("Earnings ₦100.07")).toBeVisible();
    expect(screen.getByText("Available to pay: ₦25.03")).toBeVisible();
    await user.click(screen.getByRole("checkbox"));
    await user.click(screen.getByRole("button", { name: "Review selected payments" }));
    expect(calls.preview).toHaveBeenCalledWith("NGN", [entry.ledger_entry_id]);
  });

  it("clears the saved draft when all selected earnings settle as deductions", async () => {
    calls.preview.mockResolvedValue({
      currency: "NGN",
      earnings_amount: "100.07",
      deduction_amount: "100.07",
      total_amount: "0.00",
    });
    calls.reserve.mockResolvedValue({ done: "Nothing needs sending." });
    const user = userEvent.setup();
    render(<CreateBatchForm entries={[entry]} actorId="maker" />);
    await user.click(screen.getByRole("checkbox"));
    await user.type(
      screen.getByRole("textbox", { name: "Payment run reason" }),
      "Settle next payout",
    );
    await user.click(screen.getByRole("button", { name: "Review selected payments" }));
    await screen.findByText(/To bank/);
    await user.click(screen.getByRole("button", { name: "Create payment run" }));
    expect(await screen.findByRole("status")).toHaveTextContent("Nothing needs sending.");
    expect(localStorage.getItem("cardvert-payout-draft:maker")).toBeNull();
    expect(screen.queryByRole("link", { name: /payment run/ })).toBeNull();
  });

  it("requires a server preview and retains exact recovery before a lost response", async () => {
    render(<CreateBatchForm entries={[entry]} actorId="maker" />);
    const user = userEvent.setup();
    await user.click(screen.getByRole("checkbox"));
    await user.type(
      screen.getByRole("textbox", { name: "Payment run reason" }),
      "Staff payment review",
    );
    expect(screen.getByRole("button", { name: "Create payment run" })).toBeDisabled();
    await user.click(screen.getByRole("button", { name: "Review selected payments" }));
    expect(calls.preview).toHaveBeenCalledWith("NGN", [entry.ledger_entry_id]);
    expect(await screen.findByText(/To bank/)).toHaveTextContent("100.07");
    await user.click(await screen.findByRole("button", { name: "Create payment run" }));
    await screen.findByRole("alert");
    const request = calls.reserve.mock.calls[0]![1] as FormData;
    const saved = JSON.parse(localStorage.getItem("cardvert-payout-draft:maker")!);
    expect(saved.requestId).toBe(request.get("request_id"));
    expect(saved.ledgerEntryIds).toEqual([entry.ledger_entry_id]);
    await user.click(await screen.findByRole("button", { name: "Try again" }));
    await vi.waitFor(() => expect(calls.reserve).toHaveBeenCalledTimes(2));
    expect((calls.reserve.mock.calls[1]![1] as FormData).get("request_id")).toBe(saved.requestId);
    expect(screen.getByRole("checkbox")).toBeDisabled();
  });

  it("keeps the run form and per-earning extras out of sight until needed", async () => {
    render(
      <CreateBatchForm entries={[{ ...entry, bank_account_version_id: "v" }]} actorId="maker" />,
    );
    expect(screen.queryByRole("textbox", { name: "Payment run reason" })).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /Create and reserve|Review selected/ }),
    ).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Show bank details" })).not.toBeVisible();
    expect(screen.getByText("Take money off this trip")).not.toBeVisible();
    await userEvent.click(screen.getByText("More"));
    expect(screen.getByRole("button", { name: "Show bank details" })).toBeVisible();
    expect(screen.getByText("Take money off this trip")).toBeVisible();
    await userEvent.click(screen.getByRole("checkbox"));
    expect(screen.getByRole("textbox", { name: "Payment run reason" })).toBeVisible();
    expect(screen.getByRole("button", { name: "Review selected payments" })).toBeVisible();
  });

  it("restores another tab's saved selection without replacing it", async () => {
    const saved = {
      requestId: "11111111-1111-4111-8111-111111111111",
      currency: "NGN",
      ledgerEntryIds: [entry.ledger_entry_id],
      reason: "Staff payment review",
    };
    localStorage.setItem("cardvert-payout-draft:maker", JSON.stringify(saved));
    render(<CreateBatchForm entries={[entry]} actorId="maker" />);
    expect(await screen.findByRole("button", { name: "Try again" })).toBeEnabled();
    await fillReasons();
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    await vi.waitFor(() => expect(calls.reserve).toHaveBeenCalledTimes(1));
    expect((calls.reserve.mock.calls[0]![1] as FormData).get("request_id")).toBe(saved.requestId);
  });

  it("blocks held and mixed-currency selections", async () => {
    render(
      <CreateBatchForm
        entries={[
          entry,
          { ...entry, ledger_entry_id: "44444444-4444-4444-8444-444444444444", currency: "USD" },
          {
            ...entry,
            ledger_entry_id: "55555555-5555-4555-8555-555555555555",
            eligible: false,
            ineligibility_reasons: ["Active review hold"],
          },
        ]}
        actorId="maker"
      />,
    );
    const boxes = screen.getAllByRole("checkbox");
    expect(boxes[2]).toBeDisabled();
    await fillReasons();
    await userEvent.click(boxes[0]!);
    expect(boxes[1]).toBeDisabled();
    expect(screen.getByText("On hold while a trip review is open")).toBeVisible();
  });

  it("does not mutate when preview or safe recovery is unavailable", async () => {
    calls.preview.mockResolvedValue({ error: "No current assessment" });
    render(<CreateBatchForm entries={[entry]} actorId="maker" />);
    await fillReasons();
    await userEvent.click(screen.getByRole("checkbox"));
    await fillReasons();
    await userEvent.click(screen.getByRole("button", { name: "Review selected payments" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("No current assessment");
    expect(calls.reserve).not.toHaveBeenCalled();
  });

  it("labels queueing as queueing, without a paid confirmation", async () => {
    calls.transition.mockResolvedValue({
      done: "Sending started. Check each payment for the result.",
    });
    render(<BatchActions batchId="11111111-1111-4111-8111-111111111111" status="reserved" />);
    await fillReasons();
    await userEvent.click(screen.getByRole("button", { name: "Send payments" }));
    expect(await screen.findByRole("status")).toHaveTextContent(
      "Check each payment for the result.",
    );
  });

  it("offers no second approval once the run is approved, keeping void and queueing", async () => {
    render(
      <BatchActions batchId="11111111-1111-4111-8111-111111111111" status="reserved" approved />,
    );
    expect(screen.queryByRole("button", { name: "Approve payment run" })).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Reason")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Cancel this payment run" })).toBeVisible();
    expect(screen.getByRole("button", { name: "Send payments" })).toBeVisible();
  });

  it("links terminal-failure replacement separately from ambiguous submission recovery", async () => {
    calls.transition.mockResolvedValue({
      done: "Replacement ready. Approve it to send.",
      batchId: "replacement",
    });
    render(<BatchActions batchId="original" status="reconciled" />);
    expect(
      screen.getByText(/To retry a failed payment, update the driver's bank details first/),
    ).toBeVisible();
    await fillReasons();
    await userEvent.click(
      screen.getByRole("button", { name: "Request replacement for failed payments" }),
    );
    expect(await screen.findByRole("link", { name: "Review replacement run" })).toHaveAttribute(
      "href",
      "/admin/money?tab=runs&batch=replacement",
    );
  });

  it("does not create a draft without safe multi-tab locking", async () => {
    Object.defineProperty(navigator, "locks", { configurable: true, value: undefined });
    render(<CreateBatchForm entries={[entry]} actorId="maker" />);
    await fillReasons();
    await userEvent.click(screen.getByRole("checkbox"));
    await fillReasons();
    await userEvent.click(screen.getByRole("button", { name: "Review selected payments" }));
    await screen.findByText(/To bank/);
    await fillReasons();
    await userEvent.click(screen.getByRole("button", { name: "Create payment run" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "This browser can't create payment runs.",
    );
    expect(calls.reserve).not.toHaveBeenCalled();
  });

  it("refuses a different draft while an ambiguous saved request exists", async () => {
    localStorage.setItem(
      "cardvert-payout-draft:maker",
      JSON.stringify({
        requestId: "11111111-1111-4111-8111-111111111111",
        currency: "NGN",
        ledgerEntryIds: [entry.ledger_entry_id],
        reason: "Staff payment review",
      }),
    );
    render(
      <CreateBatchForm entries={[entry]} actorId="maker" draftId="different" draftCurrency="NGN" />,
    );
    await fillReasons();
    await userEvent.click(await screen.findByRole("button", { name: "Try again" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Finish your last payment run first",
    );
    expect(calls.reserve).not.toHaveBeenCalled();
  });

  it("allows explicit selection recovery only within the authoritative same draft", async () => {
    const draftId = "11111111-1111-4111-8111-111111111111";
    localStorage.setItem(
      "cardvert-payout-draft:maker",
      JSON.stringify({
        requestId: draftId,
        currency: "NGN",
        ledgerEntryIds: [entry.ledger_entry_id],
        reason: "Staff payment review",
      }),
    );
    render(
      <CreateBatchForm entries={[entry]} actorId="maker" draftId={draftId} draftCurrency="NGN" />,
    );
    await fillReasons();
    await userEvent.click(screen.getByRole("button", { name: "Change selection" }));
    expect(localStorage.getItem("cardvert-payout-draft:maker")).toBeNull();
    await fillReasons();
    await userEvent.click(screen.getByRole("checkbox"));
    await fillReasons();
    await userEvent.click(screen.getByRole("button", { name: "Review selected payments" }));
    await fillReasons();
    await userEvent.click(await screen.findByRole("button", { name: "Create payment run" }));
    await vi.waitFor(() => expect(calls.reserve).toHaveBeenCalledTimes(1));
    expect((calls.reserve.mock.calls[0]![1] as FormData).get("request_id")).toBe(draftId);
  });

  it("does not reveal a destination when the operator cancels the audited read", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(false);
    render(<MaskedDestination versionId="version" />);
    await fillReasons();
    await userEvent.click(screen.getByRole("button", { name: "Show bank details" }));
    expect(calls.mask).not.toHaveBeenCalled();
  });

  it("requires explicit mask review and removes it when hidden", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    calls.mask.mockResolvedValue({ mask: "GTBank · account ending 6789" });
    render(<MaskedDestination versionId="11111111-1111-4111-8111-111111111111" />);
    expect(calls.mask).not.toHaveBeenCalled();
    await fillReasons();
    await userEvent.click(screen.getByRole("button", { name: "Show bank details" }));
    expect(await screen.findByText(/account ending 6789/)).toBeVisible();
    await fillReasons();
    await userEvent.click(screen.getByRole("button", { name: "Hide" }));
    expect(screen.queryByText(/account ending 6789/)).not.toBeInTheDocument();
  });
});

async function fillReasons() {
  for (const box of screen.queryAllByRole("textbox")) {
    const input = box as HTMLTextAreaElement;
    if (!input.disabled && !input.value) await userEvent.type(input, "Staff payment review");
  }
}
