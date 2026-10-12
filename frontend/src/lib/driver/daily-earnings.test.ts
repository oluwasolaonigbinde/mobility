import { describe, expect, it } from "vitest";
import type { components } from "@/lib/api/schema";
import { dailyEarnings, watDay } from "./daily-earnings";

type Entry = components["schemas"]["EarningsLedgerEntryRead"];
const entry = (changes: Partial<Entry> = {}): Entry => ({
  id: "one",
  amount: "10.01",
  currency: "NGN",
  campaign_id: "c",
  driver_profile_id: "d",
  vehicle_id: null,
  trip_session_id: "t",
  entry_type: "trip_payout",
  status: "available",
  occurred_at: "2026-10-09T23:30:00Z",
  created_at: "2026-10-10T00:00:00Z",
  payout_calculation_id: "p",
  description: null,
  work_days: [{ day: "2026-10-09", amount: "10.01" }],
  paid_at: null,
  paying_tonight: false,
  payment_on_hold: false,
  ...changes,
});
const show = (...entries: Entry[]) => dailyEarnings(entries, new Set());
describe("honest daily earnings", () => {
  it("nets exact decimals and persisted work days, not occurrence dates", () => {
    expect(
      show(
        entry(),
        entry({
          id: "two",
          amount: "0.02",
          work_days: [{ day: "2026-10-09", amount: "0.02" }],
          entry_type: "reversal",
        }),
      )?.[0],
    ).toMatchObject({ day: "2026-10-09", amount: "9.99", status: "Being checked" });
  });
  it("splits midnight from persisted allocations and separates currencies", () => {
    const days = show(
      entry({
        work_days: [
          { day: "2026-10-09", amount: "5.00" },
          { day: "2026-10-10", amount: "5.01" },
        ],
      }),
      entry({ currency: "USD" }),
    );
    expect(days?.map((day) => [day.day, day.currency, day.amount])).toEqual([
      ["2026-10-10", "NGN", "5.01"],
      ["2026-10-09", "NGN", "5.00"],
      ["2026-10-09", "USD", "10.01"],
    ]);
  });
  it("requires successful transfer date even if ledger says paid", () => {
    expect(show(entry({ status: "paid" }))?.[0]?.status).toBe("On hold – contact support");
    expect(show(entry({ status: "paid", paid_at: "2026-10-10T23:30:00Z" }))?.[0]?.status).toBe(
      "Paid 11 Oct",
    );
    expect(show(entry({ status: "paid", paid_at: "2026-10-10T23:30:00Z" }))?.[0]?.paidAt).toBe(
      "2026-10-10T23:30:00Z",
    );
  });
  it("uses latest payment date only if all contributing entries are paid", () => {
    const paid = entry({ status: "paid", paid_at: "2026-10-09T20:00:00Z" });
    expect(show(paid, entry({ id: "correction", entry_type: "adjustment" }))?.[0]?.status).toBe(
      "Being checked",
    );
    expect(
      show(paid, entry({ id: "second", status: "paid", paid_at: "2026-10-10T20:00:00Z" }))?.[0]
        ?.status,
    ).toBe("Paid 10 Oct");
  });
  it("requires every contributing amount to be scheduled tonight", () => {
    expect(show(entry({ paying_tonight: true }))?.[0]?.status).toBe("Paying tonight");
    expect(show(entry({ paying_tonight: true }), entry({ id: "two" }))?.[0]?.status).toBe(
      "Being checked",
    );
  });
  it.each(["pending", "available", "paid"] as const)(
    "holds override %s payment labels",
    (status) => {
      expect(
        show(
          entry({
            status,
            paying_tonight: true,
            payment_on_hold: true,
            paid_at: "2026-10-09T20:00:00Z",
          }),
        )?.[0]?.status,
      ).toBe("On hold – contact support");
      expect(
        show(
          entry({
            status,
            paying_tonight: true,
            payment_on_hold: true,
            paid_at: "2026-10-09T20:00:00Z",
          }),
        )?.[0]?.paidAt,
      ).toBeNull();
    },
  );
  it("joins public holds to unpaid earnings", () => {
    expect(dailyEarnings([entry({ status: "pending" })], new Set(["t"]))?.[0]?.status).toBe(
      "On hold – contact support",
    );
    expect(dailyEarnings([entry()], new Set(["t"]))?.[0]?.status).toBe("On hold – contact support");
  });
  it("suppresses amounts for absent or inconsistent allocations", () => {
    expect(show(entry({ work_days: [] }))).toBeNull();
    expect(show(entry({ amount: "99.00" }))).toBeNull();
    expect(show(entry({ amount: "NaN" }))).toBeNull();
  });
  it("nets a reversed original with its reversal and ignores debt provenance", () => {
    const days = show(
      entry({
        amount: "100.00",
        status: "reversed",
        work_days: [{ day: "2026-10-09", amount: "100.00" }],
      }),
      entry({
        id: "reversal",
        amount: "20.00",
        entry_type: "reversal",
        work_days: [{ day: "2026-10-09", amount: "20.00" }],
      }),
      entry({ id: "debt", amount: "20.00", entry_type: "debt_remainder", work_days: [] }),
    );
    expect(days).toMatchObject([
      { day: "2026-10-09", amount: "80.00", status: "On hold – contact support" },
    ]);
    expect(show(entry({ status: "voided" }))).toEqual([]);
  });
  it("uses Nigeria's date across midnight", () =>
    expect(watDay(new Date("2026-10-09T23:30:00Z"))).toBe("2026-10-10"));
});
