import { describe, expect, it } from "vitest";
import { dailyRateFormSchema } from "./schema";

const CAMPAIGN_ID = "7f9c1f4e-8a5b-4c3d-9e2f-1a2b3c4d5e6f";

describe("dailyRateFormSchema", () => {
  const future = new Date(Date.now() + 3_600_000).toISOString().slice(0, 16);
  const valid = {
    campaign_id: CAMPAIGN_ID,
    daily_rate_naira: "10000",
    daily_target_miles: "70",
    shortfall_strategy: "per_mile_deduction",
    deduction_per_mile_naira: "140",
    minimum_miles: "0",
    outside_area_weight: "0.5",
    effective_from: future,
    reason: "synthetic",
  };
  const firstError = (overrides: Record<string, string>) => {
    const result = dailyRateFormSchema.safeParse({ ...valid, ...overrides });
    return result.success ? null : result.error.issues[0]?.message;
  };

  it("accepts complete values and converts the start to UTC", () => {
    const result = dailyRateFormSchema.parse(valid);
    expect(result.effective_from).toMatch(/Z$/);
    expect(result.deduction_per_mile_naira).toBe("140");
    expect(
      dailyRateFormSchema.parse({
        ...valid,
        shortfall_strategy: "proportional",
        deduction_per_mile_naira: "",
      }).deduction_per_mile_naira,
    ).toBeNull();
  });

  it("requires every value and never fills one in", () => {
    expect(firstError({ daily_rate_naira: "" })).toBe("Day rate is required");
    expect(firstError({ minimum_miles: "" })).toBe("Minimum miles is required");
    expect(firstError({ outside_area_weight: "" })).toBe("Miles outside the area is required");
    expect(firstError({ shortfall_strategy: "" })).toBe("Choose how shorter days are paid");
    expect(firstError({ reason: " " })).toMatch(/reason is required/);
  });

  it("checks the strategy, deduction, weight, minimum and start", () => {
    expect(firstError({ deduction_per_mile_naira: "" })).toBe(
      "Enter the amount taken off for each missing mile",
    );
    expect(firstError({ shortfall_strategy: "proportional" })).toMatch(/Leave the per-mile/);
    expect(firstError({ outside_area_weight: "1.5" })).toMatch(/from 0 to 1/);
    expect(firstError({ minimum_miles: "71" })).toBe(
      "Minimum miles cannot be more than the daily miles",
    );
    expect(firstError({ daily_rate_naira: "0" })).toBe("The day rate must be more than 0");
    expect(firstError({ effective_from: "2020-01-01T00:00" })).toMatch(/must be in the future/);
  });
});
