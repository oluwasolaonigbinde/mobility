import { describe, expect, it } from "vitest";
import type { components } from "@/lib/api/schema";
import { recordedBudget, combineBudgets, moneyMinor, minorDecimal } from "./budget-display";
type Evaluation = components["schemas"]["BudgetEvaluationRead"];
const campaign = { id: "campaign", currency: "NGN", budget_amount: "1000.00" };
const evaluation = {
  campaign_id: "campaign",
  currency: "NGN",
  campaign_budget_amount: "1000.00",
  budget_basis: "total",
  billing_spend_amount: "200.03",
  evaluated_at: "2026-10-18T10:00:00Z",
  state: "within_budget",
} as Evaluation;
describe("recorded campaign spending", () => {
  it("uses exact total-budget billing spend and retains its recorded time", () => {
    expect(recordedBudget(campaign, [evaluation])).toEqual({
      spent: BigInt(20003),
      budget: BigInt(100000),
      currency: "NGN",
      evaluatedAt: evaluation.evaluated_at,
    });
    expect(minorDecimal(moneyMinor("9007199254740991.03")!)).toBe("9007199254740991.03");
  });
  it.each([
    { budget_basis: "daily" },
    { state: "blocked_external_policy" },
    { state: "unknown" },
    { external_gate: "MISSING" },
    { campaign_budget_amount: "999.99" },
    { currency: "USD" },
    { campaign_id: "other" },
    { billing_spend_amount: null },
    { billing_spend_amount: "-1.00" },
    { evaluated_at: "bad date" },
  ])("withholds unavailable or mismatched spending %j", (change) => {
    expect(recordedBudget(campaign, [{ ...evaluation, ...change }])).toBeNull();
  });
  it("does not fall back to an older good evaluation after a later blocked one", () => {
    expect(
      recordedBudget(campaign, [
        evaluation,
        { ...evaluation, state: "blocked_external_policy", evaluated_at: "2026-10-18T11:00:00Z" },
      ]),
    ).toBeNull();
  });
  it("aggregates only complete same-currency readings, with the oldest time", () => {
    const first = recordedBudget(campaign, [evaluation])!;
    const next = { ...first, spent: BigInt(10001), evaluatedAt: "2026-10-18T09:00:00Z" };
    expect(combineBudgets([first, next])).toEqual({
      ...first,
      spent: BigInt(30004),
      budget: BigInt(200000),
      evaluatedAt: next.evaluatedAt,
    });
    expect(combineBudgets([first, null])).toBeNull();
    expect(combineBudgets([first, { ...next, currency: "USD" }])).toBeNull();
    expect(combineBudgets([])).toBeNull();
  });
  it.each([null, "", "NaN", "-2", "1.123", "1e3"])("rejects invalid money %s", (value) =>
    expect(moneyMinor(value)).toBeNull(),
  );
});
