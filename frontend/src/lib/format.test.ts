import { describe, expect, it } from "vitest";
import { formatCount, formatMoney, formatScore, formatKm } from "./format";

describe("formatCount", () => {
  it("formats decimal strings from the API", () => {
    expect(formatCount("18521.43")).toBe("18,521");
  });
  it("handles null/undefined/garbage as em dash", () => {
    expect(formatCount(null)).toBe("—");
    expect(formatCount(undefined)).toBe("—");
    expect(formatCount("not-a-number")).toBe("—");
  });
});

describe("formatMoney", () => {
  it("formats NGN amounts", () => {
    expect(formatMoney("13389.00", "NGN")).toContain("13,389");
  });
  it("keeps decimals for small amounts only", () => {
    expect(formatMoney("12.50", "NGN")).toContain("12.5");
    expect(formatMoney("125000", "NGN")).not.toContain(".");
  });
  it("returns em dash for absent values", () => {
    expect(formatMoney(null)).toBe("—");
  });
});

describe("formatScore", () => {
  it("renders 0-1 scores as percentages", () => {
    expect(formatScore("0.87")).toBe("87%");
    expect(formatScore(1)).toBe("100%");
  });
});

describe("formatKm", () => {
  it("converts meters to km", () => {
    expect(formatKm("128000")).toBe("128 km");
  });
});
