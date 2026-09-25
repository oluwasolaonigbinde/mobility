import { describe, expect, it } from "vitest";
import { describeSource, labelFor, optionLabel, sourceTypeLabel } from "./labels";

describe("retargeting labels", () => {
  it("describes a declared audience in plain words", () => {
    expect(
      describeSource({
        source_type: "website-traffic",
        audience_category: "conversion-intent",
        aggregation_window_days: 30,
      }),
    ).toBe("Close to buying · last 30 days");
    expect(describeSource({ channel: "social", campaign_stage: "awareness" })).toBe(
      "Social media · Just becoming aware",
    );
    expect(describeSource({ record_count_band: "1000-plus" })).toBe("1,000 people or more");
  });

  it("returns nothing for a missing snapshot and falls back to readable raw values", () => {
    expect(describeSource(null)).toBe("");
    expect(describeSource("not-an-object")).toBe("");
    expect(labelFor(sourceTypeLabel, "UTM-source")).toBe("Tracked link (UTM) traffic");
    expect(labelFor(optionLabel, "future_new-value")).toBe("future new value");
  });
});
