import { describe, expect, it } from "vitest";
import { CATEGORY_LABELS, PARTY_CATEGORIES, formatWat, referenceText } from "./labels";

describe("complaint labels", () => {
  it("shows times in Nigeria time regardless of the server clock", () => {
    expect(formatWat("2026-09-03T07:15:00Z")).toBe("3 Sep 2026, 08:15 WAT");
    expect(formatWat(null)).toBe("—");
    expect(formatWat("not a date")).toBe("—");
  });

  it("offers each party only its own categories, all labelled", () => {
    expect(PARTY_CATEGORIES.driver).not.toContain("billing_or_invoice");
    expect(PARTY_CATEGORIES.advertiser).not.toContain("pay_or_payout");
    for (const category of [...PARTY_CATEGORIES.driver, ...PARTY_CATEGORIES.advertiser]) {
      expect(CATEGORY_LABELS[category]).toBeTruthy();
    }
  });
});

describe("reference text", () => {
  it("names the record without repeating the kind", () => {
    expect(referenceText("trip", "Trip on 3 Sep 2026")).toBe("Trip on 3 Sep 2026");
    expect(referenceText("campaign", "Launch")).toBe("Campaign: Launch");
    expect(referenceText("payout", "Trip pay ₦10")).toBe("Payout: Trip pay ₦10");
    expect(referenceText("payout", null)).toBe("Payout (details unavailable)");
    expect(referenceText(null, null)).toBe("No record chosen");
  });
});
