import { expect, it } from "vitest";
import { frozenJob } from "./frozen-job";
const terms = {
  campaign_window_start_at: "2026-10-01T00:00:00Z",
  campaign_window_end_at: "2026-11-01T00:00:00Z",
  currency: "NGN",
  payout: { formula_version: "payout_v4", daily_rate_naira: "10000.00", currency: "NGN" },
  zones: {
    target: [{ name: "Wuse II" }, { name: "Maitama" }, { name: "Wuse II" }],
    exclusion: [{ name: "Airport restricted area" }],
  },
};
it("reads the agreed dates, rate, currency and area names without mutable campaign data", () => {
  expect(frozenJob(terms)).toEqual({
    startAt: terms.campaign_window_start_at,
    endAt: terms.campaign_window_end_at,
    rate: "10000.00",
    currency: "NGN",
    areas: ["Wuse II", "Maitama"],
    excluded: ["Airport restricted area"],
  });
});
it.each([undefined, null, {}, { zones: { target: [{ name: "Wuse II" }, {}] } }])(
  "does not invent paying areas when terms are absent or incomplete",
  (value) => expect(frozenJob(value).areas).toBeNull(),
);
it("rejects malformed dates/rate/currency", () => {
  expect(
    frozenJob({
      ...terms,
      campaign_window_start_at: "soon",
      payout: { formula_version: "unknown", daily_rate_naira: "10000" },
      currency: "garbage",
    }),
  ).toMatchObject({ startAt: null, rate: null, currency: null });
});
it.each([undefined, null, [{ name: "Airport restricted area" }, {}], "unreadable"])(
  "preserves unavailable exclusions instead of claiming none",
  (exclusion) => {
    expect(frozenJob({ ...terms, zones: { ...terms.zones, exclusion } }).excluded).toBeNull();
  },
);
it("distinguishes an explicitly empty exclusion list", () => {
  expect(frozenJob({ ...terms, zones: { ...terms.zones, exclusion: [] } }).excluded).toEqual([]);
});
