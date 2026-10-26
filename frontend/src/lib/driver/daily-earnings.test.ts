import { describe, expect, it } from "vitest";
import type { components } from "@/lib/api/schema";
import { presentEarningsDay, watDay } from "./daily-earnings";

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
  it("uses Nigeria's date across midnight", () =>
    expect(watDay(new Date("2026-10-09T23:30:00Z"))).toBe("2026-10-10"));
});
