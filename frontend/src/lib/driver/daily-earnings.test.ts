import { describe, expect, it } from "vitest";
import type { components } from "@/lib/api/schema";
import { addMoney, paidBeforeDeduction, presentEarningsDay, watDay } from "./daily-earnings";

type Day = components["schemas"]["DriverEarningsDayRead"];
const day = (changes: Partial<Day> = {}): Day => ({
  day: "2026-10-09",
  currency: "NGN",
  amount: "10.01",
  status: "being_checked",
  paid_at: null,
  trip_ids: ["t"],
  ...changes,
});

describe("daily earnings words", () => {
  it.each([
    [day({ status: "on_hold" }), "On hold – contact support"],
    [day({ status: "paid", paid_at: "2026-10-10T23:30:00Z" }), "Paid 11 Oct"],
    [day({ status: "paying_tonight" }), "Paying tonight"],
    [day(), "Being checked"],
  ])("labels %o as %s", (input, label) => {
    expect(presentEarningsDay(input).status).toBe(label);
  });
  it("keeps the server's exact amount, payment date and trips", () => {
    expect(
      presentEarningsDay(day({ status: "paid", paid_at: "2026-10-10T23:30:00Z" })),
    ).toMatchObject({ amount: "10.01", paidAt: "2026-10-10T23:30:00Z", tripIds: ["t"] });
  });
  it("shows the cash paid and the deduction still to come (REQ-256)", () => {
    expect(
      presentEarningsDay(
        day({
          amount: "9900.00",
          overpaid: "100.00",
          status: "paid",
          paid_at: "2026-10-25T20:00:00Z",
        }),
      ),
    ).toMatchObject({ amount: "10000.00", status: "Paid 25 Oct · ₦100.00 to be deducted" });
  });
  it("shows the plain net once the deduction is taken", () => {
    expect(
      presentEarningsDay(
        day({
          amount: "9900.00",
          overpaid: "0.00",
          status: "paid",
          paid_at: "2026-10-25T20:00:00Z",
        }),
      ),
    ).toMatchObject({ amount: "9900.00", status: "Paid 25 Oct" });
  });
  it("shows a deduction alone on a day with no pay of its own", () => {
    expect(
      presentEarningsDay(
        day({
          amount: "-100.00",
          overpaid: "100.00",
          status: "paid",
          paid_at: "2026-10-25T20:00:00Z",
        }),
      ),
    ).toMatchObject({ amount: "-100.00", status: "₦100.00 to be deducted" });
  });
  it("keeps other states and adds exactly in kobo", () => {
    expect(
      presentEarningsDay(day({ amount: "10400.10", overpaid: "0.20", status: "on_hold" })),
    ).toMatchObject({
      amount: "10400.30",
      status: "On hold – contact support · ₦0.20 to be deducted",
    });
    expect(addMoney("0.10", "0.20")).toBe("0.30");
  });
  it("words a trip paid before its deduction in one line", () =>
    expect(paidBeforeDeduction("9900.00", "100.00", "NGN")).toBe(
      "₦10,000.00 paid · ₦100.00 to be deducted",
    ));
  it("uses Nigeria's date across midnight", () =>
    expect(watDay(new Date("2026-10-09T23:30:00Z"))).toBe("2026-10-10"));
});
