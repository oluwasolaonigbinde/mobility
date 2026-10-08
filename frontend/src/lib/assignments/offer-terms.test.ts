import { describe, expect, it } from "vitest";
import { installationViewLabel } from "./installation-views";
import { dailyRateSentences, offerTermLines } from "./offer-terms";

describe("offerTermLines", () => {
  it("lists every accepted term in words without IDs, hashes, geometry or versions", () => {
    const lines = offerTermLines({
      offer_terms_version: "offer_terms_v3",
      currency: "NGN",
      campaign_window_start_at: "2026-10-01T08:00:00+00:00",
      service_area: { city: "Abuja", country_code: "NG" },
      branding: { campaign_id: "c1", campaign_name: "Wuse Blitz", brand_name: null },
      payout: {
        revision_id: "r1",
        formula_version: "payout_v3",
        hourly_rate_naira: "1500.00",
        premium_hourly_rate_naira: "",
        missing_rate_naira: null,
        eligibility_params: { stationary_window_min: 5 },
      },
      zones: {
        semantics: "target_zones_are_premium",
        target: [{ id: "z1", name: "Wuse II", wkt: "MULTIPOLYGON(((0 0)))" }],
        exclusion: [],
      },
      eligibility: { stationary_policy_marker: "stationary-rd-v1", teleport_kmh: 180 },
      accepted: true,
      shifts: ["morning", "evening"],
    });

    const text = lines.map((line) => `${line.label}: ${line.value}`).join("\n");
    expect(text).toContain("Currency: NGN");
    expect(text).toContain("Service area · City: Abuja");
    expect(text).toContain("Branding · Campaign name: Wuse Blitz");
    expect(text).toContain("Payout · Hourly rate naira: ₦1,500.00");
    expect(text).toContain("Payout · Eligibility params · Stationary window min: 5");
    expect(text).toContain("Zones · Target: Wuse II");
    expect(text).toContain("Eligibility · Teleport kmh: 180");
    expect(text).toContain("Accepted: Yes");
    expect(text).toContain("Shifts: morning, evening");
    expect(text).toMatch(/Campaign window start at: \d/);
    expect(text).not.toMatch(
      /c1|r1|z1|MULTIPOLYGON|payout_v3|offer_terms_v3|stationary-rd|semantics/,
    );
    expect(text).not.toContain("Brand name");
    expect(text).not.toContain("Exclusion");
    expect(text).not.toMatch(/Premium hourly rate|Missing rate|₦0.00/);
  });
});

describe("installationViewLabel", () => {
  it("names the client's five views and falls back to words for other codes", () => {
    expect(["front", "back", "left", "right", "close_up"].map(installationViewLabel)).toEqual([
      "Front",
      "Back",
      "Left side",
      "Right side",
      "Close-up of the branding",
    ]);
    expect(installationViewLabel("rear_window")).toBe("Rear window");
  });
});

describe("dailyRateSentences", () => {
  const offer = (payout: Record<string, unknown>) => ({
    payout: {
      formula_version: "payout_v4",
      daily_rate_naira: "10000.00",
      daily_target_miles: "70.000",
      shortfall_strategy: "proportional",
      deduction_per_mile_naira: null,
      minimum_miles: "0.000",
      outside_area_weight: "1.0000",
      ...payout,
    },
    eligibility: {
      stationary_policy_marker: "d39-stop-5min-v1",
      stationary_window_seconds: 300,
      max_ping_gap_seconds: 120,
    },
  });

  it("states the day rate, target, proportional rule, stop rule and full outside miles", () => {
    expect(dailyRateSentences(offer({}))).toEqual([
      "₦10,000.00 for a full day of 70 miles.",
      "Driving more than 70 miles in a day still earns ₦10,000.00.",
      "Shorter days are paid in proportion to the miles covered.",
      "Stops of up to 5 minutes count as driving; longer stops add no miles.",
      "No miles are counted while your phone loses its location for more than 2 minutes.",
      "Miles outside the campaign area count in full.",
    ]);
  });

  it("states the per-mile deduction, the minimum and the outside-area share", () => {
    const sentences = dailyRateSentences(
      offer({
        shortfall_strategy: "per_mile_deduction",
        deduction_per_mile_naira: "140.00",
        minimum_miles: "20.000",
        outside_area_weight: "0.5000",
      }),
    );
    expect(sentences).toContain("Each mile short of 70 takes ₦140.00 off the day's pay.");
    expect(sentences).toContain("Days under 20 miles are not paid.");
    expect(sentences).toContain("Miles outside the campaign area count at 50%.");
    expect(dailyRateSentences(offer({ outside_area_weight: "0.0000" }))).toContain(
      "Only miles inside the campaign area count.",
    );
  });

  it("returns nothing for hourly offers and hides the raw daily-rate keys", () => {
    expect(dailyRateSentences({ payout: { formula_version: "payout_v3" } })).toEqual([]);
    const text = offerTermLines(offer({}))
      .map((line) => `${line.label}: ${line.value}`)
      .join("\n");
    expect(text).not.toMatch(/Daily rate naira|Daily target miles|Shortfall|Outside area weight/);
    expect(text).toContain("Eligibility · Stationary window seconds: 300");
  });
});
