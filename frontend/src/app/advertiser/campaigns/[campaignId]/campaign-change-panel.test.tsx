import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  confirm: vi.fn(),
  preview: vi.fn(),
}));

vi.mock("./actions", () => ({
  confirmCampaignChangeAction: mocks.confirm,
  previewCampaignChangeAction: mocks.preview,
}));

import { CampaignChangePanel } from "./campaign-change-panel";

const CAMPAIGN_ID = "00000000-0000-4000-8000-00000000000a";
const FIRST_REQUEST_ID = "00000000-0000-4000-8000-00000000000b";
const SECOND_REQUEST_ID = "00000000-0000-4000-8000-00000000000c";

describe("CampaignChangePanel", () => {
  beforeEach(() => {
    mocks.preview.mockImplementation(async (_state: unknown, form: FormData) => ({
      commandId: String(form.get("client_request_id")),
      preview: {
        after: { budget_amount: String(form.get("budget_amount")) },
        available_liability_amount: "5000.00",
        before: { budget_amount: "1000.00" },
        classifications: ["budget_increase"],
        currency: "NGN",
        outcome: "apply_now",
        preview_sha256: "b".repeat(64),
        requested_liability_amount: "100.00",
        source_sha256: "a".repeat(64),
      },
      proposal: {
        budgetAmount: String(form.get("budget_amount")),
        reason: String(form.get("reason")),
      },
    }));
    mocks.confirm.mockImplementation(async (_state: unknown, form: FormData) => {
      const commandId = String(form.get("client_request_id"));
      return {
        commandId,
        confirmedRequest: {
          classifications: ["budget_increase"],
          client_request_id: commandId,
          created_at: "2026-09-14T12:00:00Z",
          id: commandId,
          requested_liability_amount: "100.00",
          status: "applied",
        },
        done: "Campaign change confirmed.",
      };
    });
    vi.stubGlobal("crypto", { randomUUID: vi.fn(() => SECOND_REQUEST_ID) });
  });

  afterEach(() => vi.unstubAllGlobals());

  it("starts a fresh command after success and supports a second change without reload", async () => {
    const user = userEvent.setup();
    render(
      <CampaignChangePanel
        campaignId={CAMPAIGN_ID}
        clientRequestId={FIRST_REQUEST_ID}
        currency="NGN"
        requests={[]}
      />,
    );

    await user.type(screen.getByLabelText("Total budget"), "1100.00");
    await user.type(screen.getByLabelText("Reason"), "First expansion");
    await user.click(screen.getByRole("button", { name: "Preview change" }));
    await user.click(await screen.findByRole("button", { name: "Confirm this change" }));

    await waitFor(() => expect(screen.queryByLabelText("Change preview")).not.toBeInTheDocument());
    await user.clear(screen.getByLabelText("Total budget"));
    await user.type(screen.getByLabelText("Total budget"), "1200.00");
    await user.clear(screen.getByLabelText("Reason"));
    await user.type(screen.getByLabelText("Reason"), "Second expansion");
    await user.click(screen.getByRole("button", { name: "Preview change" }));
    await user.click(await screen.findByRole("button", { name: "Confirm this change" }));

    await waitFor(() => expect(mocks.confirm).toHaveBeenCalledTimes(2));
    const submittedIds = mocks.confirm.mock.calls.map((call) =>
      String((call[1] as FormData).get("client_request_id")),
    );
    expect(submittedIds).toEqual([FIRST_REQUEST_ID, SECOND_REQUEST_ID]);
  });
});
