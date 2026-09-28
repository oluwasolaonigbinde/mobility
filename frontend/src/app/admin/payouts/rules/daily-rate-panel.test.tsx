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
    hourly_rate_naira: null,
    premium_hourly_rate_naira: null,
    daily_payable_hours_cap: null,
    daily_rate_naira: "10000.00",
    daily_target_miles: "70.000",
    shortfall_strategy: "per_mile_deduction",
    deduction_per_mile_naira: "140.00",
    minimum_miles: "0.000",
    outside_area_weight: "0.5000",
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
        publishingEnabled
        revisions={[
          revision({ revision_number: 2, id: "00000000-0000-4000-8000-000000000002" }),
          revision({
            formula_version: "payout_v3",
            hourly_rate_naira: "1200.00",
            daily_rate_naira: null,
            shortfall_strategy: null,
            reason: "earlier hourly pay",
          }),
        ]}
      />,
    );

    for (const label of [
      "Day rate (₦)",
      "Daily miles for a full day",
      "Shorter days are paid",
      "Deduction per missing mile (₦, per-mile rule only)",
      "Minimum miles for any pay (0 for none)",
      "Share of miles outside the campaign area that count (0 to 1)",
      "Starts (future)",
      "Reason (audited)",
    ]) {
      expect(screen.getByLabelText(label)).toBeInTheDocument();
    }
    const headers = screen.getAllByRole("columnheader").map((cell) => cell.textContent);
    expect(headers).toEqual([
      "#",
      "Starts",
      "Day rate",
      "Daily miles",
      "Shorter days",
      "Minimum",
      "Outside area",
      "Reason",
    ]);
    expect(headers.join(" ")).not.toMatch(/hour/i);
    const [daily, hourly] = screen.getAllByRole("row").slice(1);
    if (!daily || !hourly) throw new Error("expected two rows");
    expect(within(daily).getByText(/10,000\.00/)).toBeInTheDocument();
    expect(within(daily).getByText("70")).toBeInTheDocument();
    expect(within(daily).getByText(/140\.00 off per missing mile/)).toBeInTheDocument();
    expect(within(daily).getByText("Count at 50%")).toBeInTheDocument();
    expect(within(hourly).getByText(/Earlier hourly terms: .*1,200\.00\/hour/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Publish daily rate" })).toBeEnabled();
  });

  it("shows the empty history and the not-switched-on state with the form disabled", () => {
    render(<DailyRatePanel campaignId={CAMPAIGN_ID} publishingEnabled={false} revisions={[]} />);

    expect(screen.getByText("No pay revisions for this campaign yet.")).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("Daily-rate pay is not switched on yet.");
    expect(screen.getByLabelText("Day rate (₦)")).toBeDisabled();
    expect(screen.getByRole("button", { name: "Publish daily rate" })).toBeDisabled();
  });

  it("keeps typed values and shows a field error, a retryable error and success", () => {
    actionState.current = {
      error: "Enter the amount taken off for each missing mile",
      field: "deduction_per_mile_naira",
      values: { daily_rate_naira: "9800", shortfall_strategy: "per_mile_deduction" },
    };
    const { rerender } = render(
      <DailyRatePanel campaignId={CAMPAIGN_ID} publishingEnabled revisions={[]} />,
    );
    const deduction = screen.getByLabelText("Deduction per missing mile (₦, per-mile rule only)");
    expect(deduction).toHaveAttribute("aria-invalid", "true");
    expect(screen.getByRole("alert")).toHaveTextContent(
      "Enter the amount taken off for each missing mile",
    );
    expect(screen.getByLabelText("Day rate (₦)")).toHaveValue("9800");

    actionState.current = { error: "Could not reach the server. Try again.", values: {} };
    rerender(<DailyRatePanel campaignId={CAMPAIGN_ID} publishingEnabled revisions={[]} />);
    expect(screen.getByRole("alert")).toHaveTextContent("Could not reach the server. Try again.");
    expect(screen.getByRole("button", { name: "Publish daily rate" })).toBeEnabled();

    actionState.current = { notSwitchedOn: true };
    rerender(<DailyRatePanel campaignId={CAMPAIGN_ID} publishingEnabled revisions={[]} />);
    expect(screen.getByRole("status")).toHaveTextContent("not switched on yet");

    actionState.current = { created: true };
    rerender(<DailyRatePanel campaignId={CAMPAIGN_ID} publishingEnabled revisions={[]} />);
    expect(screen.getByText(/Daily rate published/)).toBeInTheDocument();
  });

  it("shows the pending state while publishing", () => {
    actionState.pending = true;
    render(<DailyRatePanel campaignId={CAMPAIGN_ID} publishingEnabled revisions={[]} />);
    expect(screen.getByRole("button", { name: "Publishing…" })).toBeDisabled();
  });
});
