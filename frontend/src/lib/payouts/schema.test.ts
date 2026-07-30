import { describe, expect, it } from "vitest";
import { ruleFormSchema } from "./schema";

const CAMPAIGN_ID = "7f9c1f4e-8a5b-4c3d-9e2f-1a2b3c4d5e6f";

const empty = {
  campaign_id: CAMPAIGN_ID,
  rule_id: "",
  base_rate_per_km: "",
  base_rate_per_active_hour: "",
  target_zone_bonus_rate_per_km: "",
  bonus_zone_bonus_rate_per_km: "",
  estimated_impression_rate_per_1000: "",
  min_payout_per_trip: "",
  max_payout_per_trip: "",
  low_fraud_multiplier: "",
  medium_fraud_multiplier: "",
  high_fraud_multiplier: "",
  hourly_rate_naira: "",
  daily_payable_hours_cap: "",
};

describe("ruleFormSchema — payout_v2 (hourly + daily cap)", () => {
  it("accepts a complete hourly rule", () => {
    const parsed = ruleFormSchema.safeParse({
      ...empty,
      formula_version: "payout_v2",
      hourly_rate_naira: "1200.00",
      daily_payable_hours_cap: "8",
    });
    expect(parsed.success).toBe(true);
    if (parsed.success) {
      expect(parsed.data.hourly_rate_naira).toBe("1200.00");
      expect(parsed.data.daily_payable_hours_cap).toBe("8");
    }
  });

  it("requires the hourly rate", () => {
    const parsed = ruleFormSchema.safeParse({
      ...empty,
      formula_version: "payout_v2",
      daily_payable_hours_cap: "8",
    });
    expect(parsed.success).toBe(false);
    if (!parsed.success) {
      expect(parsed.error.issues[0]?.message).toMatch(/hourly rate/i);
    }
  });

  it("requires the daily cap (D4: shown in the driver's offer)", () => {
    const parsed = ruleFormSchema.safeParse({
      ...empty,
      formula_version: "payout_v2",
      hourly_rate_naira: "1200",
    });
    expect(parsed.success).toBe(false);
  });

  it("bounds the cap to 24 hours", () => {
    const parsed = ruleFormSchema.safeParse({
      ...empty,
      formula_version: "payout_v2",
      hourly_rate_naira: "1200",
      daily_payable_hours_cap: "25",
    });
    expect(parsed.success).toBe(false);
  });

  it("rejects legacy per-km fields on an hourly rule (model XOR)", () => {
    const parsed = ruleFormSchema.safeParse({
      ...empty,
      formula_version: "payout_v2",
      hourly_rate_naira: "1200",
      daily_payable_hours_cap: "8",
      base_rate_per_km: "55",
    });
    expect(parsed.success).toBe(false);
    if (!parsed.success) {
      expect(parsed.error.issues[0]?.message).toMatch(/legacy per-km/i);
    }
  });
});

describe("ruleFormSchema — payout_v1 (legacy per-km)", () => {
  it("accepts a sparse v1 rule (defaults fill on the backend)", () => {
    const parsed = ruleFormSchema.safeParse({
      ...empty,
      formula_version: "payout_v1",
      base_rate_per_km: "55",
    });
    expect(parsed.success).toBe(true);
  });

  it("rejects hourly fields on a v1 rule (model XOR)", () => {
    const parsed = ruleFormSchema.safeParse({
      ...empty,
      formula_version: "payout_v1",
      hourly_rate_naira: "1200",
    });
    expect(parsed.success).toBe(false);
    if (!parsed.success) {
      expect(parsed.error.issues[0]?.message).toMatch(/hourly fields/i);
    }
  });

  it("still validates multipliers as 0–1", () => {
    const parsed = ruleFormSchema.safeParse({
      ...empty,
      formula_version: "payout_v1",
      low_fraud_multiplier: "1.5",
    });
    expect(parsed.success).toBe(false);
  });
});
