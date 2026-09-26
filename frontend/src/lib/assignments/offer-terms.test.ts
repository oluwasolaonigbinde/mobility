import { describe, expect, it } from "vitest";
import { installationViewLabel } from "./installation-views";
import { offerTermLines } from "./offer-terms";

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
    expect(text).toContain("Payout · Hourly rate naira: 1500.00");
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
