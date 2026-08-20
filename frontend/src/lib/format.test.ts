import { describe, expect, it } from "vitest";
import {
  formatCount,
  formatDuration,
  formatMoney,
  formatDateTime,
  formatMoneyExact,
  formatScore,
  formatKm,
} from "./format";

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

describe("formatDuration", () => {
  it("formats hours and minutes", () => {
    expect(formatDuration(9660)).toBe("2h 41m");
    expect(formatDuration("3600")).toBe("1h 0m");
  });

  it("formats sub-hour and sub-minute values", () => {
    expect(formatDuration(2460)).toBe("41m");
    expect(formatDuration(59)).toBe("59s");
    expect(formatDuration(0)).toBe("0s");
  });

  it("dashes out nullish and invalid values", () => {
    expect(formatDuration(null)).toBe("—");
    expect(formatDuration(undefined)).toBe("—");
    expect(formatDuration("not-a-number")).toBe("—");
    expect(formatDuration(-5)).toBe("—");
  });
});

describe("formatMoneyExact", () => {
  it("never rounds kobo away", () => {
    expect(formatMoneyExact("9600.50")).toContain("9,600.50");
    expect(formatMoneyExact("1250.50")).toContain("1,250.50");
    expect(formatMoneyExact(null)).toBe("—");
  });
});

describe("formatDateTime", () => {
  it("shows the wall-clock time for rate-flip instants", () => {
    const out = formatDateTime("2026-08-15T09:30:00Z");
    expect(out).toMatch(/2026/);
    expect(out).toMatch(/:/);
  });

  it("dashes for missing or invalid input", () => {
    expect(formatDateTime(null)).toBe("\u2014");
    expect(formatDateTime("garbage")).toBe("\u2014");
  });
});
