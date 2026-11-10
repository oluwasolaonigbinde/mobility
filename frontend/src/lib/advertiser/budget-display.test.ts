import { expect, it } from "vitest";
import { remainingBudget, wholeMoney, campaignBudgets } from "./budget-display";
const c = {
  currency: "NGN",
  budget_amount: "1128750.00",
  start_at: "2026-11-01T00:00:00+01:00",
  end_at: "2026-11-30T23:59:00+01:00",
  status: "active",
};
it.each([
  [1, "1091125"],
  [10, "752500"],
  [30, "0"],
])("day %s counts today", (day, amount) =>
  expect(
    remainingBudget(c, new Date(`2026-11-${String(day).padStart(2, "0")}T12:00Z`)).remaining,
  ).toBe(BigInt(amount) * 100n),
);
it("840000 on day 21 of 28 is 210000", () =>
  expect(
    remainingBudget(
      { ...c, budget_amount: "840000", end_at: "2026-11-28T22:59Z" },
      new Date("2026-11-21T12:00Z"),
    ).remaining,
  ).toBe(21000000n));
it.each(["draft", "pending_review", "approved", "rejected"])("%s keeps full budget", (status) =>
  expect(remainingBudget({ ...c, status }).remaining).toBe(112875000n),
);
it.each([
  [{ status: "finished" }, 0n],
  [{ status: "cancelled" }, null],
  [{ status: "paused", pause_kind: "budget" }, null],
  [{ budget_amount: null }, null],
  [{ budget_amount: "0" }, null],
  [{ budget_amount: "bad" }, null],
  [{ end_at: "invalid" }, null],
])("fails closed or ends correctly %j", (patch, expected) =>
  expect(remainingBudget({ ...c, ...patch }, new Date("2026-11-10T12:00Z")).remaining).toBe(
    expected,
  ),
);
it("uses Nigeria midnight and floors display without decimals", () => {
  expect(remainingBudget(c, new Date("2026-11-09T23:00Z")).remaining).toBe(75250000n);
  expect(wholeMoney(12399n, "NGN")).toBe("₦123");
  expect(remainingBudget(c, new Date("2026-10-31T12:00Z")).remaining).toBe(112875000n);
});
it("sums each currency separately and poisons only malformed currency group", () => {
  const result = campaignBudgets(
    [{ ...c, currency: "USD" }, { ...c, budget_amount: "bad" }, c],
    new Date("2026-11-10T12:00Z"),
  );
  expect(result).toEqual([
    { currency: "USD", budget: 112875000n, remaining: 75250000n },
    { currency: "NGN", budget: null, remaining: null },
  ]);
});
it.each(["active", "paused"])("day 3 for %s leaves 27 of 30 days", (status) =>
  expect(remainingBudget({ ...c, status }, new Date("2026-11-03T12:00Z")).remaining).toBe(
    101587500n,
  ),
);
it("missing dates keeps the full budget", () =>
  expect(remainingBudget({ ...c, start_at: null }).remaining).toBe(112875000n));

it("retains the known currency total when a budget pause makes remaining unavailable", () =>
  expect(campaignBudgets([{ ...c, pause_kind: "budget" }], new Date("2026-11-10T12:00Z"))).toEqual([
    { currency: "NGN", budget: 112875000n, remaining: null },
  ]));

it.each(["bad", "-1", "-100.00"])(
  "invalid included total %s makes its currency unavailable",
  (budget_amount) => {
    expect(campaignBudgets([c, { ...c, budget_amount }], new Date("2026-11-10T12:00Z"))).toEqual([
      { currency: "NGN", budget: null, remaining: null },
    ]);
  },
);
