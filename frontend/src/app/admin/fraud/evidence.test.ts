import { describe, expect, it } from "vitest";
import { readableEvidence } from "./evidence";

describe("readableEvidence", () => {
  it("reads each detector's evidence as a sentence", () => {
    expect(
      readableEvidence({
        max_observed_speed_mps: 539.9865,
        offending_segment_count: 3,
        threshold_mps: 55,
      }),
    ).toEqual(["Top speed 1,944 km/h (limit 198 km/h)", "3 stretches over the speed limit"]);
    expect(readableEvidence({ valid_ping_count: 4, min_valid_pings: 10 })).toEqual([
      "4 usable location points (at least 10 needed)",
    ]);
    expect(
      readableEvidence({
        poor_accuracy_ratio: 0.425,
        poor_accuracy_ping_count: 17,
        threshold_ratio: 0.3,
      }),
    ).toEqual(["42.5% of location points had poor GPS accuracy (17 points); limit 30%"]);
    expect(
      readableEvidence({ stationary_seconds: 1800, stationary_ratio: 0.75, threshold_ratio: 0.5 }),
    ).toEqual(["Stationary for 75% of the trip (30 min); limit 50%"]);
    expect(
      readableEvidence({ max_gap_seconds: 900, gap_count: 2, threshold_seconds: 300 }),
    ).toEqual(["Longest gap between location points 15 min (limit 5 min); 2 long gaps"]);
    expect(readableEvidence({ future_ping_count: 6, future_skew_seconds: 300 })).toEqual([
      "6 location points timed in the future (more than 5 min ahead)",
    ]);
    expect(
      readableEvidence({
        start_end_distance_m: 40,
        total_distance_m: 12500,
        looping_radius_m: 150,
        looping_min_distance_m: 2000,
      }),
    ).toEqual(["Ended 40 m from where it started after 12.5 km"]);
    expect(
      readableEvidence({ exclusion_zone_distance_m: 820, exclusion_zone_seconds: 95 }),
    ).toEqual(["820 m, 95 s inside an excluded area"]);
  });

  it("hides seed bookkeeping and keeps unknown evidence readable", () => {
    expect(
      readableEvidence({
        demo: true,
        seed_version: "f7_rich_v1",
        verification_id: "check-1",
        result: { observed: "no wrap" },
      }),
    ).toEqual(["Verification id: check-1", 'Result: {"observed":"no wrap"}']);
    expect(readableEvidence(null)).toEqual([]);
    expect(readableEvidence({ demo: true })).toEqual([]);
  });

  it("keeps a partial reading when a limit is missing and falls back when a value is", () => {
    expect(readableEvidence({ max_observed_speed_mps: 40 })).toEqual(["Top speed 144 km/h"]);
    expect(readableEvidence({ threshold_mps: 55 })).toEqual(["Threshold mps: 55"]);
    expect(readableEvidence({ valid_ping_count: 4 })).toEqual(["4 usable location points"]);
    expect(readableEvidence({ poor_accuracy_ratio: 0.5 })).toEqual([
      "50% of location points had poor GPS accuracy",
    ]);
    expect(readableEvidence({ stationary_ratio: 0.6 })).toEqual(["Stationary for 60% of the trip"]);
    expect(readableEvidence({ max_gap_seconds: 45 })).toEqual([
      "Longest gap between location points 45 s",
    ]);
    expect(readableEvidence({ future_ping_count: 2 })).toEqual([
      "2 location points timed in the future",
    ]);
    expect(readableEvidence({ exclusion_zone_seconds: 600 })).toEqual([
      "10 min inside an excluded area",
    ]);
    expect(readableEvidence({ exclusion_zone_distance_m: 2400 })).toEqual([
      "2.4 km inside an excluded area",
    ]);
  });

  it("uses the singular for a count of one", () => {
    expect(readableEvidence({ max_gap_seconds: 1200, gap_count: 1 })).toEqual([
      "Longest gap between location points 20 min; 1 long gap",
    ]);
    expect(readableEvidence({ offending_segment_count: 1 })).toEqual([
      "1 stretch over the speed limit",
    ]);
    expect(readableEvidence({ future_ping_count: 1 })).toEqual([
      "1 location point timed in the future",
    ]);
    expect(readableEvidence({ valid_ping_count: 1 })).toEqual(["1 usable location point"]);
  });

  it("falls back to label and value when a known key holds something unexpected", () => {
    expect(
      readableEvidence({
        offending_segment_count: "many",
        start_end_distance_m: 12,
        stationary_seconds: "long",
        future_skew_seconds: 300,
        gap_count: 3,
        exclusion_zone_seconds: null,
      }),
    ).toEqual([
      "Offending segment count: many",
      "Start end distance m: 12",
      "Stationary seconds: long",
      "Future skew seconds: 300",
      "Gap count: 3",
      "Exclusion zone seconds: null",
    ]);
    expect(readableEvidence({ nested: { deep: "x".repeat(200) } })[0]).toHaveLength(
      "Nested: ".length + 118,
    );
  });
});
