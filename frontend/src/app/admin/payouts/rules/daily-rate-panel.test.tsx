import { render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { components } from "@/lib/api/schema";
import type { DailyRateActionState } from "./actions";

const { actionState } = vi.hoisted(() => ({
  actionState: { current: {} as DailyRateActionState, pending: false },
}));

vi.mock("./actions", () => ({ publishDailyRateAction: vi.fn() }));
vi.mock("react", async (importOriginal) => {
  const react = await importOriginal<typeof import("react")>();
  return {
    ...react,
    useActionState: () => [actionState.current, vi.fn(), actionState.pending],
  };
});

import { DailyRatePanel } from "./daily-rate-panel";

type Revision = components["schemas"]["CampaignPayoutRuleRevisionRead"];

const CAMPAIGN_ID = "7f9c1f4e-8a5b-4c3d-9e2f-1a2b3c4d5e6f";

function revision(overrides: Partial<Revision>): Revision {
  return {
    id: "00000000-0000-4000-8000-000000000001",
    campaign_id: CAMPAIGN_ID,
    payout_rule_id: "2a6d8e1b-4c3f-4a5d-8e9f-0a1b2c3d4e5f",
    revision_number: 1,
    effective_from: "2026-10-01T07:00:00Z",
    daily_rate_naira: "10000.00",
    daily_target_miles: "70.000",
    shortfall_strategy: "proportional",
    deduction_per_mile_naira: null,
    minimum_miles: "0.000",
    outside_area_weight: "0.0000",
    currency: "NGN",
    eligibility_params: { stationary_window_min: 5, stationary_grace_min: 0 },
    formula_version: "payout_v4",
    reason: "synthetic test values",
    created_by_user_id: "11111111-2222-4333-8444-555555555555",
    created_at: "2026-09-27T00:00:00Z",
    ...overrides,
  };
}

describe("DailyRatePanel", () => {
  beforeEach(() => {
    actionState.current = {};
    actionState.pending = false;
  });

  it("labels every input and shows its own columns for daily-rate rows", () => {
    render(
      <DailyRatePanel
        campaignId={CAMPAIGN_ID}

        revisions={[revision({ revision_number: 2, id: "00000000-0000-4000-8000-000000000002" })]}
      />,
    );

    for (const label of [
      "Day rate (₦)",
      "Daily miles for a full day",
      "Starts (future)",
      "Reason",
    ]) {
      expect(screen.getByLabelText(label)).toBeInTheDocument();
    }
    expect(screen.queryByRole("combobox")).toBeNull();
    expect(screen.queryByLabelText(/Deduction|Minimum miles|Share of miles/)).toBeNull();
    const headers = screen.getAllByRole("columnheader").map((cell) => cell.textContent);
    expect(headers).toEqual(["#", "Starts", "Day rate", "Daily miles", "Reason"]);
    expect(headers.join(" ")).not.toMatch(/hour/i);
    const [daily] = screen.getAllByRole("row").slice(1);
    if (!daily) throw new Error("expected daily row");
    expect(within(daily).getByText(/10,000\.00/)).toBeInTheDocument();
    expect(within(daily).getByText("70")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Publish daily rate" })).toBeEnabled();
  });

  it("allows publication with an empty history", () => {
    render(<DailyRatePanel campaignId={CAMPAIGN_ID} revisions={[]} />);

    expect(screen.getByText("No pay versions for this campaign yet.")).toBeInTheDocument();
    expect(screen.getByLabelText("Day rate (₦)")).toBeEnabled();
    expect(screen.getByRole("button", { name: "Publish daily rate" })).toBeEnabled();
  });

  it("keeps typed values and shows a field error, a retryable error and success", () => {
    actionState.current = {
      error: "Enter the daily miles",
      field: "daily_target_miles",
      values: { daily_rate_naira: "9800", daily_target_miles: "" },
    };
    const { rerender } = render(<DailyRatePanel campaignId={CAMPAIGN_ID} revisions={[]} />);
    const target = screen.getByLabelText("Daily miles for a full day");
    expect(target).toHaveAttribute("aria-invalid", "true");
    expect(screen.getByRole("alert")).toHaveTextContent("Enter the daily miles");
    expect(screen.getByLabelText("Day rate (₦)")).toHaveValue("9800");

    actionState.current = { error: "Could not reach the server. Try again.", values: {} };
    rerender(<DailyRatePanel campaignId={CAMPAIGN_ID} revisions={[]} />);
    expect(screen.getByRole("alert")).toHaveTextContent("Could not reach the server. Try again.");
    expect(screen.getByRole("button", { name: "Publish daily rate" })).toBeEnabled();

    actionState.current = { created: true };
    rerender(<DailyRatePanel campaignId={CAMPAIGN_ID} revisions={[]} />);
    expect(screen.getByText(/Daily rate published/)).toBeInTheDocument();
  });

  it("shows the pending state while publishing", () => {
    actionState.pending = true;
    render(<DailyRatePanel campaignId={CAMPAIGN_ID} revisions={[]} />);
    expect(screen.getByRole("button", { name: "Publishing…" })).toBeDisabled();
  });
});
