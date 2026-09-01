import { describe, expect, it } from "vitest";
import {
  BRAND_POINTS,
  CARDVERT,
  CONTACT,
  DRIVER_POINTS,
  MAILTO,
  PILOT_FACTS,
  REPORT,
  SERVICES,
  STEPS,
  TAGLINE,
} from "./content";

/**
 * Claim guard. The landing page may only say what the brand documents and the
 * confirmed client answers say. These assertions fail loudly if approved
 * contact details drift or if superseded/ungranted claims creep back in.
 */
describe("landing content", () => {
  it("preserves the approved contact details exactly", () => {
    expect(CONTACT.email).toBe("terraxmediacompany@gmail.com");
    expect(CONTACT.domain).toBe("terraxmedia.com");
    expect(CONTACT.socialHandle).toBe("Terramedia_company");
    expect(CONTACT.productDomain).toBe("Cardvert.com");
    expect(TAGLINE).toBe("Driving Impact Beyond Locations");
  });

  it("sends every call to action to the business address", () => {
    for (const href of Object.values(MAILTO)) {
      expect(href.startsWith(`mailto:${CONTACT.email}?`)).toBe(true);
      expect(href).toContain("subject=");
    }
  });

  it("keeps the pilot shape as confirmed (Q30)", () => {
    expect(PILOT_FACTS.map((f) => f.value)).toEqual(["Abuja", "10", "5", "3 months"]);
  });

  it("labels report rows as measured or modelled, never blended", () => {
    for (const row of REPORT.rows) {
      expect(["Measured", "Modelled"]).toContain(row.kind);
    }
    expect(REPORT.footnote).toMatch(/optional/i);
  });

  const allCopy = [
    ...SERVICES.flatMap((s) => [s.title, s.body, s.note]),
    ...BRAND_POINTS.flatMap((p) => [p.title, p.body]),
    ...DRIVER_POINTS.flatMap((p) => [p.title, p.body]),
    ...STEPS.flatMap((s) => [s.title, s.brand, s.driver]),
    ...CARDVERT.points,
    CARDVERT.lead,
    CARDVERT.footnote,
  ].join(" ");

  it.each([
    // D18/Q5 replaced mileage pay with fixed hourly base/premium zone pay.
    ["mileage pay", /mileage|per kilometre|per km\b/i],
    // Q10 defers native background tracking to after the pilot.
    ["background tracking as a current feature", /background gps|tracks in the background/i],
    // Q11 keeps live ad-platform push disabled.
    [
      "live ad-platform activation",
      /automatically push|live retargeting|sync to meta|sync to google/i,
    ],
    // Nothing in the source documents supports store distribution or AI counting.
    // (Saying an app-store account is *not* needed is fine; claiming a listing is not.)
    [
      "app store availability",
      /(download|available|get it|find us) on (the )?(app store|google play)/i,
    ],
    ["AI counting", /\bai\b.*count|computer vision/i],
  ])("does not claim %s", (_label, pattern) => {
    expect(allCopy).not.toMatch(pattern);
  });

  it("states the Cardvert pilot limitation rather than hiding it", () => {
    expect(CARDVERT.footnote).toMatch(/screen on/i);
    expect(CARDVERT.footnote).toMatch(/after the pilot/i);
  });
});
