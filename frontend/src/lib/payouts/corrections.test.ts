import { describe, expect, it } from "vitest";
import { correctionOrderFormSchema, summarizeProjectedDelta } from "./corrections";

const CAMPAIGN_ID = "7f9c1f4e-8a5b-4c3d-9e2f-1a2b3c4d5e6f";

describe("correctionOrderFormSchema", () => {
  it("accepts campaign + Lagos day (reason may be empty for projection)", () => {
    const parsed = correctionOrderFormSchema.safeParse({
      campaign_id: CAMPAIGN_ID,
      lagos_day: "2026-08-15",
      reason: "",
    });
    expect(parsed.success).toBe(true);
  });

  it("rejects a malformed day", () => {
    const parsed = correctionOrderFormSchema.safeParse({
      campaign_id: CAMPAIGN_ID,
      lagos_day: "15/08/2026",
      reason: "x",
    });
    expect(parsed.success).toBe(false);
  });

  it("rejects a missing campaign", () => {
    const parsed = correctionOrderFormSchema.safeParse({
      campaign_id: "",
      lagos_day: "2026-08-15",
      reason: "",
    });
    expect(parsed.success).toBe(false);
  });
});

describe("summarizeProjectedDelta", () => {
  const backendShape = {
    currencies: ["NGN"],
    trips: [],
    day_totals: {
      previous_posted_amount: "9600.00",
      target_amount: "10450.50",
      delta_amount: "850.50",
      projected_adjustment_count: 2,
      projected_reversal_count: 1,
      trip_count: 3,
    },
  };

  it("summarizes the backend day_totals shape", () => {
    expect(summarizeProjectedDelta(backendShape)).toEqual({
      previousTotal: "9600.00",
      targetTotal: "10450.50",
      deltaTotal: "850.50",
      adjustmentCount: 2,
      reversalCount: 1,
      tripCount: 3,
      currency: "NGN",
    });
  });

  it("returns null for a missing or malformed projection", () => {
    expect(summarizeProjectedDelta(null)).toBeNull();
    expect(summarizeProjectedDelta(undefined)).toBeNull();
    expect(summarizeProjectedDelta({})).toBeNull();
    expect(summarizeProjectedDelta({ day_totals: { delta_amount: 850 } })).toBeNull();
  });

  it("defaults counts and currency when absent", () => {
    const summary = summarizeProjectedDelta({
      day_totals: {
        previous_posted_amount: "0.00",
        target_amount: "0.00",
        delta_amount: "0.00",
      },
    });
    expect(summary).toMatchObject({ adjustmentCount: 0, reversalCount: 0, currency: "NGN" });
  });
});
