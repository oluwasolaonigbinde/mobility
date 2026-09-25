import { describe, expect, it } from "vitest";
import {
  campaignBasicsSchema,
  creativeSchema,
  toApiDatetime,
  toLagosDatetimeLocal,
} from "./schema";

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
  it("accepts only a creative with a cleared managed file", () => {
    const parsed = creativeSchema.parse({
      name: "Full wrap",
      creative_type: "image",
      placement: "vehicle_exterior",
      stored_file_id: "00000000-0000-4000-8000-000000000001",
      original_filename: "wrap.png",
    });
    expect(parsed.stored_file_id).toBe("00000000-0000-4000-8000-000000000001");
  });

  it("rejects missing managed files and unknown enums", () => {
    expect(
      creativeSchema.safeParse({
        name: "x",
        creative_type: "image",
        placement: "vehicle_exterior",
        stored_file_id: "",
        original_filename: "",
      }).success,
    ).toBe(false);
    expect(
      creativeSchema.safeParse({
        name: "x",
        creative_type: "billboard",
        placement: "vehicle_exterior",
        stored_file_id: "00000000-0000-4000-8000-000000000001",
        original_filename: "wrap.png",
      }).success,
    ).toBe(false);
  });
});

describe("toApiDatetime", () => {
  it("reads datetime-local input as Lagos time whatever the runtime zone", () => {
    expect(toApiDatetime(undefined)).toBeUndefined();
    expect(toApiDatetime("2026-08-01T08:00")).toBe("2026-08-01T07:00:00.000Z");
    expect(toApiDatetime("2026-12-31T23:30:15")).toBe("2026-12-31T22:30:15.000Z");
  });

  it("round-trips a stored instant through the Lagos form default", () => {
    expect(toLagosDatetimeLocal("2026-08-01T07:00:00Z")).toBe("2026-08-01T08:00");
    expect(toApiDatetime(toLagosDatetimeLocal("2026-08-01T07:00:00Z"))).toBe(
      "2026-08-01T07:00:00.000Z",
    );
    expect(toLagosDatetimeLocal(null)).toBe("");
    expect(toLagosDatetimeLocal("not a date")).toBe("");
  });

  it("rejects zoned or offset strings that are not datetime-local values", () => {
    const basics = { name: "Launch", description: "", budget_amount: "", daily_budget_amount: "" };
    for (const value of ["2026-08-01T08:00Z", "2026-08-01T08:00+02:00", "2026-08-01"]) {
      expect(
        campaignBasicsSchema.safeParse({ ...basics, start_at: value, end_at: "" }).success,
      ).toBe(false);
    }
  });
});
