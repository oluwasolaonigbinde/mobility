import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
const { get } = vi.hoisted(() => ({ get: vi.fn() }));
vi.mock("@/lib/api/client", () => ({ createApiClient: () => ({ GET: get }) }));
vi.mock("@/lib/auth/session", () => ({ getSessionToken: async () => "token" }));
vi.mock("../payouts/rules/rule-form", () => ({ RuleForm: () => <p>Legacy editor</p> }));
vi.mock("../payouts/rules/revisions-panel", () => ({ RevisionsPanel: () => <p>Hourly editor</p> }));
vi.mock("../payouts/rules/daily-rate-panel", () => ({ DailyRatePanel: () => <p>Daily editor</p> }));
import Section from "./pay-terms-section";
import { readPayTerms } from "./pay-terms-read";
const current = {
  id: "revision",
  payout_rule_id: "rule",
  effective_from: "2026-01-01T00:00:00Z",
  formula_version: "payout_v4",
  daily_rate_naira: "10000.00",
  daily_target_miles: "70",
  currency: "NGN",
};
function mock(version = "payout_v4", revision: Record<string, unknown> | undefined = current) {
  get.mockImplementation(async (path, options) => {
    if (path.endsWith("/payout-rules"))
      return {
        data: {
          items: [{ id: "rule", status: "active", formula_version: version, currency: "NGN" }],
        },
      };
    if (path.endsWith("/revisions"))
      return {
        data: {
          items: options.params.query.effective_before ? (revision ? [revision] : []) : [],
          total: revision ? 1 : 0,
        },
      };
    if (path.endsWith("/status")) return { data: { publishing_enabled: true } };
    throw Error("Unexpected read");
  });
}
describe("Current Pay terms", () => {
  beforeEach(() => vi.clearAllMocks());
  it("shows current daily amount and target before a collapsed editor and uses the same readiness result", async () => {
    mock();
    const terms = await readPayTerms("campaign");
    expect(terms?.ready).toBe(true);
    render(await Section({ campaignId: "campaign" }));
    expect(screen.getByText(/10,000.*per day for 70 miles/)).toBeVisible();
    expect(screen.getByText("Change pay terms").closest("details")).not.toHaveAttribute("open");
    expect(screen.queryByText("Legacy editor")).toBeNull();
    const query = get.mock.calls.find(
      ([p, o]) => p.endsWith("/revisions") && o.params.query.effective_before,
    )?.[1].params.query;
    expect(query.limit).toBe(1);
    expect(query.effective_before).toBeTruthy();
  });
  it("shows hourly rate, premium and daily cap for v3 terms on an hourly rule", async () => {
    mock("payout_v2", {
      ...current,
      formula_version: "payout_v3",
      hourly_rate_naira: "1000.00",
      premium_hourly_rate_naira: "1500.00",
      daily_payable_hours_cap: "8",
    });
    render(await Section({ campaignId: "campaign" }));
    expect(screen.getByText(/1,000.*per hour, up to 8 payable hours/)).toBeVisible();
    expect(screen.getByText(/1,500.*premium area/)).toBeVisible();
  });
  it("future-only terms never tick the launch checklist", async () => {
    mock("payout_v4", { ...current, effective_from: "2099-01-01T00:00:00Z" });
    expect((await readPayTerms("campaign"))?.ready).toBe(false);
  });
  it("failed current reads show one section failure", async () => {
    get.mockRejectedValue(new Error("offline"));
    render(await Section({ campaignId: "campaign" }));
    expect(screen.getByRole("alert")).toHaveTextContent("Couldn't load this section — try again");
  });
  it("keeps legacy terms truthful and their editor closed", async () => {
    mock("payout_v1");
    render(await Section({ campaignId: "campaign" }));
    expect(screen.getByText(/older distance and zone pay terms/)).toBeVisible();
    expect(screen.getByText("Legacy editor").closest("details")).not.toHaveAttribute("open");
  });
});
