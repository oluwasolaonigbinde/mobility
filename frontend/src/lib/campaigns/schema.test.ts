import { describe, expect, it } from "vitest";
import { campaignBasicsSchema, creativeSchema, toApiDatetime } from "./schema";

const validBasics = {
  name: "Yello Season Q3",
  description: "",
  start_at: "2026-08-01T08:00",
  end_at: "2026-09-30T20:00",
  budget_amount: "5000000",
  daily_budget_amount: "",
};

describe("campaignBasicsSchema", () => {
  it("accepts a valid campaign and normalizes empties", () => {
    const parsed = campaignBasicsSchema.parse(validBasics);
    expect(parsed.name).toBe("Yello Season Q3");
    expect(parsed.description).toBeUndefined();
    expect(parsed.daily_budget_amount).toBeUndefined();
    expect(parsed.budget_amount).toBe("5000000");
  });

  it("requires a name", () => {
    expect(campaignBasicsSchema.safeParse({ ...validBasics, name: "  " }).success).toBe(false);
  });

  it("rejects end before start", () => {
    const result = campaignBasicsSchema.safeParse({
      ...validBasics,
      start_at: "2026-09-30T20:00",
      end_at: "2026-08-01T08:00",
    });
    expect(result.success).toBe(false);
    if (!result.success) {
      expect(result.error.issues.some((i) => i.path.join(".") === "end_at")).toBe(true);
    }
  });

  it("rejects negative and malformed money", () => {
    expect(campaignBasicsSchema.safeParse({ ...validBasics, budget_amount: "-5" }).success).toBe(
      false,
    );
    expect(
      campaignBasicsSchema.safeParse({ ...validBasics, budget_amount: "12.345" }).success,
    ).toBe(false);
    expect(campaignBasicsSchema.safeParse({ ...validBasics, budget_amount: "abc" }).success).toBe(
      false,
    );
  });
});

describe("creativeSchema", () => {
  it("accepts a creative with empty URL (optional)", () => {
    const parsed = creativeSchema.parse({
      name: "Full wrap",
      creative_type: "image",
      placement: "vehicle_exterior",
      asset_url: "",
    });
    expect(parsed.asset_url).toBeUndefined();
  });

  it("rejects invalid URLs and unknown enums", () => {
    expect(
      creativeSchema.safeParse({
        name: "x",
        creative_type: "image",
        placement: "vehicle_exterior",
        asset_url: "not-a-url",
      }).success,
    ).toBe(false);
    expect(
      creativeSchema.safeParse({
        name: "x",
        creative_type: "billboard",
        placement: "vehicle_exterior",
        asset_url: "",
      }).success,
    ).toBe(false);
  });
});

describe("toApiDatetime", () => {
  it("converts datetime-local to ISO and passes undefined through", () => {
    expect(toApiDatetime(undefined)).toBeUndefined();
    const iso = toApiDatetime("2026-08-01T08:00");
    expect(iso).toMatch(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}/);
    expect(new Date(iso!).getTime()).toBe(new Date("2026-08-01T08:00").getTime());
  });
});
