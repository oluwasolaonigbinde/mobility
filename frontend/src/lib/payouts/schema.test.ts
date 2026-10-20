import { describe, expect, it } from "vitest";
import { dailyRateFormSchema } from "./schema";

const CAMPAIGN_ID = "7f9c1f4e-8a5b-4c3d-9e2f-1a2b3c4d5e6f";

describe("dailyRateFormSchema", () => {
  const future = new Date(Date.now() + 3_600_000).toISOString().slice(0, 16);
  const valid = {
    campaign_id: CAMPAIGN_ID,
    daily_rate_naira: "10000",
    daily_target_miles: "70",
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
    expect(result.daily_rate_naira).toBe("10000");
  });

  it("requires every value and never fills one in", () => {
    expect(firstError({ daily_rate_naira: "" })).toBe("Day rate is required");
    expect(firstError({ daily_target_miles: "" })).toBe("Daily miles is required");
    expect(firstError({ reason: " " })).toMatch(/reason is required/);
  });

  it("checks positive amounts and the future start", () => {
    expect(firstError({ daily_target_miles: "0" })).toBe("Daily miles must be more than 0");
    expect(firstError({ daily_rate_naira: "0" })).toBe("The day rate must be more than 0");
    expect(firstError({ effective_from: "2020-01-01T00:00" })).toMatch(/must be in the future/);
  });
});
