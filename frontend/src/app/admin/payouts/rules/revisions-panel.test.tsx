import { render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { RevisionsPanel } from "./revisions-panel";
import type { components } from "@/lib/api/schema";

vi.mock("./actions", () => ({
  createRevisionAction: vi.fn(),
  saveRuleAction: vi.fn(),
}));

type Revision = components["schemas"]["CampaignPayoutRuleRevisionRead"];

const CAMPAIGN_ID = "7f9c1f4e-8a5b-4c3d-9e2f-1a2b3c4d5e6f";
const RULE_ID = "2a6d8e1b-4c3f-4a5d-8e9f-0a1b2c3d4e5f";

function revision(overrides: Partial<Revision>): Revision {
  return {
    id: "00000000-0000-4000-8000-000000000001",
    campaign_id: CAMPAIGN_ID,
    payout_rule_id: RULE_ID,
    revision_number: 1,
    effective_from: "2026-08-01T00:00:00Z",
    hourly_rate_naira: "1200.00",
    premium_hourly_rate_naira: null,
    daily_payable_hours_cap: "8",
    currency: "NGN",
    eligibility_params: {},
    formula_version: "payout_v3",
    reason: "genesis: initial payout_v2 rule values at rule creation",
    created_by_user_id: "11111111-2222-4333-8444-555555555555",
    created_at: "2026-08-01T00:00:00Z",
    ...overrides,
  };
}

// The page passes the API's newest-first order straight through.
const revisions: Revision[] = [
  revision({
    id: "00000000-0000-4000-8000-000000000002",
    revision_number: 2,
    effective_from: "2026-09-01T06:00:00Z",
    hourly_rate_naira: "1500.00",
    premium_hourly_rate_naira: "1800.00",
    reason: "festive-season rate bump",
  }),
  revision({}),
];

describe("RevisionsPanel", () => {
  it("lists the revision chain newest-first with rates, cap, reason and creator", () => {
    render(<RevisionsPanel campaignId={CAMPAIGN_ID} ruleId={RULE_ID} revisions={revisions} />);

    const [newest, oldest] = screen.getAllByRole("row").slice(1); // drop the header row
    if (!newest || !oldest) throw new Error("expected two revision rows");
    expect(within(newest).getByText("r2")).toBeInTheDocument();
    expect(within(newest).getByText(/1,500\.00/)).toBeInTheDocument();
    expect(within(newest).getByText(/1,800\.00/)).toBeInTheDocument();
    expect(within(newest).getByText("festive-season rate bump")).toBeInTheDocument();
    expect(within(newest).getByText(/^11111111/)).toBeInTheDocument();
    expect(within(oldest).getByText("r1")).toBeInTheDocument();
    expect(within(oldest).getByText("8h")).toBeInTheDocument();
  });

  it("renders the create-revision form instead of edit-in-place", () => {
    render(<RevisionsPanel campaignId={CAMPAIGN_ID} ruleId={RULE_ID} revisions={revisions} />);

    expect(screen.getByLabelText("Base hourly rate")).toBeInTheDocument();
    expect(screen.getByLabelText("Premium hourly rate (optional)")).toBeInTheDocument();
    expect(screen.getByLabelText("Daily payable-hours cap")).toBeInTheDocument();
    expect(screen.getByLabelText("Effective from (future)")).toBeInTheDocument();
    expect(screen.getByLabelText("Reason (audited)")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Create revision" })).toBeInTheDocument();
    // Immutability messaging replaces the retired update path.
    expect(screen.queryByRole("button", { name: /update rule/i })).not.toBeInTheDocument();
    expect(screen.getByText(/values are immutable/i)).toBeInTheDocument();
  });

  it("prefills the form from the latest revision's values", () => {
    render(<RevisionsPanel campaignId={CAMPAIGN_ID} ruleId={RULE_ID} revisions={revisions} />);

    expect(screen.getByLabelText("Base hourly rate")).toHaveValue("1500.00");
    expect(screen.getByLabelText("Premium hourly rate (optional)")).toHaveValue("1800.00");
    expect(screen.getByLabelText("Daily payable-hours cap")).toHaveValue("8");
  });

  it("shows the complete versioned detector policy without live settings", () => {
    render(<RevisionsPanel campaignId={CAMPAIGN_ID} ruleId={RULE_ID} revisions={revisions} />);

    expect(screen.getByText("stationary-rd-v1 · provisional/tunable")).toBeInTheDocument();
    expect(screen.getByText(/120s windows.*120s stride.*≤25m/)).toBeInTheDocument();
    expect(screen.getByText(/Legacy 200m \/ 300s stay check.*240s trip grace/)).toBeInTheDocument();
    expect(
      screen.getByText(/Every new acceptance snapshots these complete values/),
    ).toBeInTheDocument();
  });
});
