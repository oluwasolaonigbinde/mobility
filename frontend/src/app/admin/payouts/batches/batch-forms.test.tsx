import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { BatchActions, CreateBatchForm, MaskedDestination } from "./batch-forms";
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
  allocateDebtAction: vi.fn(),
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
  currency: "NGN",
  debt_deducted: "0.00",
  carry_forward_debt: "0.00",
  destination_verified: true,
  bank_account_version_id: null,
  eligible: true,
  ineligibility_reasons: [],
};

describe("payout operator forms", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    Object.defineProperty(navigator, "locks", {
      configurable: true,
      value: { request: vi.fn(async (_key, work) => work()) },
    });
    calls.preview.mockResolvedValue({ currency: "NGN", total_amount: "100.07" });
    calls.reserve.mockResolvedValue({ error: "Lost response. Retry saved request." });
  });

  it("requires a server preview and retains exact recovery before a lost response", async () => {
    render(<CreateBatchForm entries={[entry]} actorId="maker" />);
    const user = userEvent.setup();
    await user.click(screen.getByRole("checkbox"));
    expect(
      screen.getByRole("button", { name: "Create and reserve selected credits" }),
    ).toBeDisabled();
    await user.click(screen.getByRole("button", { name: "Review selected credits" }));
    expect(calls.preview).toHaveBeenCalledWith("NGN", [entry.ledger_entry_id]);
    expect(await screen.findByText(/Advisory selected total/)).toHaveTextContent("100.07");
    await user.click(screen.getByRole("button", { name: "Create and reserve selected credits" }));
    await screen.findByRole("alert");
    const request = calls.reserve.mock.calls[0]![1] as FormData;
    const saved = JSON.parse(localStorage.getItem("cardvert-payout-draft:maker")!);
    expect(saved.requestId).toBe(request.get("request_id"));
    expect(saved.ledgerEntryIds).toEqual([entry.ledger_entry_id]);
    await user.click(await screen.findByRole("button", { name: "Retry saved reservation" }));
    await vi.waitFor(() => expect(calls.reserve).toHaveBeenCalledTimes(2));
    expect((calls.reserve.mock.calls[1]![1] as FormData).get("request_id")).toBe(saved.requestId);
    expect(screen.getByRole("checkbox")).toBeDisabled();
  });

  it("restores another tab's saved selection without replacing it", async () => {
    const saved = {
      requestId: "11111111-1111-4111-8111-111111111111",
      currency: "NGN",
      ledgerEntryIds: [entry.ledger_entry_id],
    };
    localStorage.setItem("cardvert-payout-draft:maker", JSON.stringify(saved));
    render(<CreateBatchForm entries={[entry]} actorId="maker" />);
    expect(await screen.findByRole("button", { name: "Retry saved reservation" })).toBeEnabled();
    await userEvent.click(screen.getByRole("button", { name: "Retry saved reservation" }));
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
    await userEvent.click(boxes[0]!);
    expect(boxes[1]).toBeDisabled();
    expect(screen.getByText("Active review hold")).toBeVisible();
  });

  it("does not mutate when preview or safe recovery is unavailable", async () => {
    calls.preview.mockResolvedValue({ error: "No current assessment" });
    render(<CreateBatchForm entries={[entry]} actorId="maker" />);
    await userEvent.click(screen.getByRole("checkbox"));
    await userEvent.click(screen.getByRole("button", { name: "Review selected credits" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("No current assessment");
    expect(calls.reserve).not.toHaveBeenCalled();
  });

  it("labels queueing as queueing, without a paid confirmation", async () => {
    calls.transition.mockResolvedValue({
      done: "Submission queued. This does not confirm submission or payment.",
    });
    render(<BatchActions batchId="11111111-1111-4111-8111-111111111111" status="reserved" />);
    await userEvent.click(screen.getByRole("button", { name: "Queue submission" }));
    expect(await screen.findByRole("status")).toHaveTextContent(
      "does not confirm submission or payment",
    );
  });

  it("links terminal-failure replacement separately from ambiguous submission recovery", async () => {
    calls.transition.mockResolvedValue({
      done: "Replacement reserved. Obtain independent approval.",
      batchId: "replacement",
    });
    render(<BatchActions batchId="original" status="reconciled" />);
    expect(
      screen.getByText(/Terminally failed payments require a newer verified bank/),
    ).toBeVisible();
    await userEvent.click(screen.getByRole("button", { name: "Request failed-line replacement" }));
    expect(await screen.findByRole("link", { name: "Review replacement batch" })).toHaveAttribute(
      "href",
      "/admin/payouts/batches/replacement",
    );
  });

  it("does not create a draft without safe multi-tab locking", async () => {
    Object.defineProperty(navigator, "locks", { configurable: true, value: undefined });
    render(<CreateBatchForm entries={[entry]} actorId="maker" />);
    await userEvent.click(screen.getByRole("checkbox"));
    await userEvent.click(screen.getByRole("button", { name: "Review selected credits" }));
    await screen.findByText(/Advisory selected total/);
    await userEvent.click(
      screen.getByRole("button", { name: "Create and reserve selected credits" }),
    );
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Safe multi-tab recovery is unavailable",
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
      }),
    );
    render(
      <CreateBatchForm entries={[entry]} actorId="maker" draftId="different" draftCurrency="NGN" />,
    );
    await userEvent.click(await screen.findByRole("button", { name: "Retry saved reservation" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Recover the saved batch before working on a different draft",
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
      }),
    );
    render(
      <CreateBatchForm entries={[entry]} actorId="maker" draftId={draftId} draftCurrency="NGN" />,
    );
    await userEvent.click(
      screen.getByRole("button", { name: "Review a different selection for this draft" }),
    );
    expect(localStorage.getItem("cardvert-payout-draft:maker")).toBeNull();
    await userEvent.click(screen.getByRole("checkbox"));
    await userEvent.click(screen.getByRole("button", { name: "Review selected credits" }));
    await userEvent.click(await screen.findByRole("button", { name: "Reserve this draft" }));
    await vi.waitFor(() => expect(calls.reserve).toHaveBeenCalledTimes(1));
    expect((calls.reserve.mock.calls[0]![1] as FormData).get("request_id")).toBe(draftId);
  });

  it("does not reveal a destination when the operator cancels the audited read", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(false);
    render(<MaskedDestination versionId="version" />);
    await userEvent.click(screen.getByRole("button", { name: "Review masked destination" }));
    expect(calls.mask).not.toHaveBeenCalled();
  });

  it("requires explicit mask review and removes it when hidden", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    calls.mask.mockResolvedValue({ mask: "Bank 058 · account ending 6789" });
    render(<MaskedDestination versionId="11111111-1111-4111-8111-111111111111" />);
    expect(calls.mask).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole("button", { name: "Review masked destination" }));
    expect(await screen.findByText(/account ending 6789/)).toBeVisible();
    await userEvent.click(screen.getByRole("button", { name: "Hide" }));
    expect(screen.queryByText(/account ending 6789/)).not.toBeInTheDocument();
  });
});
