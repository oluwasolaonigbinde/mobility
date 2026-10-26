import { describe, expect, it } from "vitest";
import { bookedBudget, bookedPercent, minorDecimal, moneyMinor } from "./budget-display";

const used = (amount: string, extra: Record<string, unknown> = {}) => ({
  amount,
  budget_amount: "1000.00",
  currency: "NGN",
  basis: "funding",
  as_of: "2026-10-18T10:00:00Z",
  ...extra,
});
const daily = (amount: string) => used(amount, { budget_amount: null });
const campaign = (
  budget_used: unknown,
  currency = "NGN",
  budget_amount: string | null = "1000.00",
) => ({ currency, budget_amount, budget_used }) as Parameters<typeof bookedBudget>[0];

describe("booked budget (D103)", () => {
  it("uses the exact booked figure, currency and as-of time", () => {
    expect(bookedBudget(campaign(used("200.03")))).toEqual({
      booked: BigInt(20003),
      budget: BigInt(100000),
      currency: "NGN",
      asOf: "2026-10-18T10:00:00Z",
    });
    expect(minorDecimal(moneyMinor("9007199254740991.03")!)).toBe("9007199254740991.03");
  });
  it("keeps no funding or terms as a true zero, not a dash", () => {
    expect(bookedBudget(campaign(used("0.00")))?.booked).toBe(BigInt(0));
  });
  it("reads a daily-only campaign's figure with no budget to compare against", () => {
    expect(bookedBudget(campaign(daily("25.00"), "NGN", null))).toEqual({
      booked: BigInt(2500),
      budget: null,
      currency: "NGN",
      asOf: "2026-10-18T10:00:00Z",
    });
  });
  it.each([
    null,
    undefined,
    used("-1.00"),
    used("abc"),
    used("1.00", { budget_amount: "0.00" }),
    used("1.00", { budget_amount: "bad" }),
    used("1.00", { currency: "USD" }),
    used("1.00", { as_of: "bad date" }),
  ])("shows missing or inconsistent figures as unavailable %j", (value) => {
    expect(bookedBudget(campaign(value))).toBeNull();
  });
  it("shows a dash rather than a second, different budget", () => {
    expect(bookedBudget(campaign(used("1.00"), "NGN", "900.00"))).toBeNull();
    expect(bookedBudget(campaign(used("1.00"), "NGN", null))).toBeNull();
    expect(bookedBudget(campaign(daily("1.00"), "NGN", "1000.00"))).toBeNull();
  });
  it.each([
    ["1500.00", "1000.00", 150],
    ["1000.00", "1000.00", 100],
    ["1000.01", "1000.00", 100.01],
    ["100000.01", "100000.00", 100.01],
    ["999.95", "1000.00", 99.99],
    ["99995.00", "100000.00", 99.99],
  ])(
    "percent of %s booked against %s is %s, never hiding an overrun as 100",
    (amount, budget, expected) => {
      expect(bookedPercent(moneyMinor(amount)!, moneyMinor(budget)!)).toBe(expected);
    },
  );
});

describe("money parsing", () => {
  it.each([null, "", "NaN", "-2", "1.123", "1e3"])("rejects invalid money %s", (value) =>
    expect(moneyMinor(value)).toBeNull(),
  );
});
