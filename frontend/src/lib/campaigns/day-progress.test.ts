import { expect, it } from "vitest";
import { campaignDay } from "./day-progress";

it("counts inclusive Nigeria calendar dates and clamps finished windows", () => {
  expect(campaignDay("2026-10-01T10:00Z", "2026-10-30T10:00Z", new Date("2026-10-20T10:00Z"))).toBe(
    "Day 20 of 30",
  );
  expect(campaignDay("2026-10-01T10:00Z", "2026-10-30T10:00Z", new Date("2026-11-20T10:00Z"))).toBe(
    "Day 30 of 30",
  );
  expect(campaignDay("2026-10-01T10:00Z", "2026-10-01T20:00Z", new Date("2026-10-01T11:00Z"))).toBe(
    "Day 1 of 1",
  );
  expect(campaignDay("2026-10-01T10:00Z", "2026-10-30T10:00Z", new Date("2026-10-19T23:30Z"))).toBe(
    "Day 20 of 30",
  );
});
it("uses extended dates without a separate renewal period", () => {
  expect(campaignDay("2026-10-01T10:00Z", "2026-11-30T10:00Z", new Date("2026-10-20T10:00Z"))).toBe(
    "Day 20 of 61",
  );
});
it("does not invent a counter for missing, invalid or future dates", () => {
  expect(campaignDay(null, null)).toBeNull();
  expect(campaignDay("invalid", "2026-10-01T10:00Z")).toBeNull();
  expect(campaignDay("2026-10-02T10:00Z", "2026-10-01T10:00Z")).toBeNull();
  expect(campaignDay("2026-10-01T20:00Z", "2026-10-01T10:00Z")).toBeNull();
  expect(campaignDay("2026-10-20T15:00Z", "2026-10-30T10:00Z", new Date("2026-10-20T10:00Z"))).toBe(
    "Starts 20 Oct 2026",
  );
  expect(campaignDay("2026-11-01T10:00Z", "2026-11-30T10:00Z", new Date("2026-10-20T10:00Z"))).toBe(
    "Starts 1 Nov 2026",
  );
});
