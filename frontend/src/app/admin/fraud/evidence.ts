/**
 * Turn a trip review's detection evidence into short sentences staff can read.
 * Keys come from the detectors in app/services/trip_analytics.py; anything
 * unrecognised still shows as "label: value". Seed bookkeeping keys are hidden.
 */

type Evidence = Record<string, unknown>;

const reasons: Record<string, string> = {
  insufficient_pings: "Too few usable location points",
  impossible_speed: "Speed higher than the review limit",
  poor_accuracy: "Location readings were too inaccurate",
  stationary_trip: "Too much of the trip was spent stopped",
  excessive_ping_gap: "Long gaps between location readings",
  future_timestamp: "Location readings were timed in the future",
  route_looping: "The route returned close to where it started",
  exclusion_zone_presence: "Driving recorded in an excluded area",
  route_replay: "Route matches an earlier trip",
  physical_spot_check_failed: "An in-person check found a problem",
};
export function tripReviewReason(flagType: string, evidence?: Evidence | null) {
  const title = reasons[flagType] ?? flagType.replaceAll("_", " ");
  const numbers = readableEvidence(evidence);
  return [title, ...numbers].join(" · ");
}

// Matched trips are listed on their own (see matchedTripIds); the detector version is internal.
const HIDDEN_KEYS = new Set([
  "demo",
  "seed_version",
  "detector_version",
  "sampled_matched_trip_ids",
  "verification_id",
  "gps_claim",
]);

/** Keep the check's identity on staff's secondary reference line. */
export function evidenceVerificationId(evidence: Evidence | null | undefined): string | undefined {
  return typeof evidence?.verification_id === "string" ? evidence.verification_id : undefined;
}

function checkResult(result: unknown): string[] {
  if (typeof result === "string") return result.trim() ? [result.trim()] : [];
  if (!result || typeof result !== "object" || Array.isArray(result)) return [];
  const details = result as Evidence;
  return [
    ...new Set(
      [details.observed, details.note, details.description]
        .filter((value): value is string => typeof value === "string" && Boolean(value.trim()))
        .map((value) => value.trim()),
    ),
  ];
}

/** Up to `limit` trips a route-replay review says share this trip's route. */
export function matchedTripIds(evidence: Evidence | null | undefined, limit = 3): string[] {
  const ids = evidence?.sampled_matched_trip_ids;
  return Array.isArray(ids)
    ? ids.filter((id): id is string => typeof id === "string" && id.length > 0).slice(0, limit)
    : [];
}

const whole = new Intl.NumberFormat("en-GB", { maximumFractionDigits: 0 });
const oneDecimal = new Intl.NumberFormat("en-GB", { maximumFractionDigits: 1 });

function num(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

const kmh = (mps: number) => `${whole.format(mps * 3.6)} km/h`;
const percent = (ratio: number) => `${oneDecimal.format(ratio * 100)}%`;
const duration = (seconds: number) =>
  seconds < 120 ? `${whole.format(seconds)} s` : `${whole.format(seconds / 60)} min`;
const distance = (metres: number) =>
  metres < 1000 ? `${whole.format(metres)} m` : `${oneDecimal.format(metres / 1000)} km`;
const counted = (count: number, one: string, many: string) =>
  `${whole.format(count)} ${count === 1 ? one : many}`;

/** One rule reads the keys it knows and returns a sentence, or null to leave them. */
type Rule = { keys: string[]; render: (evidence: Evidence) => string | null };

const RULES: Rule[] = [
  {
    keys: ["max_observed_speed_mps", "threshold_mps"],
    render: (e) => {
      const top = num(e.max_observed_speed_mps);
      const limit = num(e.threshold_mps);
      if (top === null) return null;
      return `Top speed ${kmh(top)}${limit === null ? "" : ` (limit ${kmh(limit)})`}`;
    },
  },
  {
    keys: ["offending_segment_count"],
    render: (e) => {
      const count = num(e.offending_segment_count);
      return count === null
        ? null
        : `${counted(count, "stretch", "stretches")} over the speed limit`;
    },
  },
  {
    keys: ["valid_ping_count", "min_valid_pings"],
    render: (e) => {
      const valid = num(e.valid_ping_count);
      const minimum = num(e.min_valid_pings);
      if (valid === null) return null;
      const needed = minimum === null ? "" : ` (at least ${whole.format(minimum)} needed)`;
      return `${counted(valid, "usable location point", "usable location points")}${needed}`;
    },
  },
  {
    keys: ["poor_accuracy_ratio", "threshold_ratio", "poor_accuracy_ping_count"],
    render: (e) => {
      const ratio = num(e.poor_accuracy_ratio);
      const limit = num(e.threshold_ratio);
      const count = num(e.poor_accuracy_ping_count);
      if (ratio === null) return null;
      const points = count === null ? "" : ` (${whole.format(count)} points)`;
      const allowed = limit === null ? "" : `; limit ${percent(limit)}`;
      return `${percent(ratio)} of location points had poor GPS accuracy${points}${allowed}`;
    },
  },
  {
    keys: ["stationary_ratio", "stationary_seconds", "threshold_ratio"],
    render: (e) => {
      const ratio = num(e.stationary_ratio);
      const seconds = num(e.stationary_seconds);
      const limit = num(e.threshold_ratio);
      if (ratio === null) return null;
      const time = seconds === null ? "" : ` (${duration(seconds)})`;
      const allowed = limit === null ? "" : `; limit ${percent(limit)}`;
      return `Stationary for ${percent(ratio)} of the trip${time}${allowed}`;
    },
  },
  {
    keys: ["max_gap_seconds", "gap_count", "threshold_seconds"],
    render: (e) => {
      const gap = num(e.max_gap_seconds);
      const count = num(e.gap_count);
      const limit = num(e.threshold_seconds);
      if (gap === null) return null;
      const gaps = count === null ? "" : `; ${counted(count, "long gap", "long gaps")}`;
      const allowed = limit === null ? "" : ` (limit ${duration(limit)})`;
      return `Longest gap between location points ${duration(gap)}${allowed}${gaps}`;
    },
  },
  {
    keys: ["future_ping_count", "future_skew_seconds"],
    render: (e) => {
      const count = num(e.future_ping_count);
      const skew = num(e.future_skew_seconds);
      if (count === null) return null;
      const allowed = skew === null ? "" : ` (more than ${duration(skew)} ahead)`;
      return `${counted(count, "location point", "location points")} timed in the future${allowed}`;
    },
  },
  {
    keys: [
      "start_end_distance_m",
      "total_distance_m",
      "looping_radius_m",
      "looping_min_distance_m",
    ],
    render: (e) => {
      const gap = num(e.start_end_distance_m);
      const total = num(e.total_distance_m);
      if (gap === null || total === null) return null;
      return `Ended ${distance(gap)} from where it started after ${distance(total)}`;
    },
  },
  {
    keys: ["exclusion_zone_distance_m", "exclusion_zone_seconds"],
    render: (e) => {
      const metres = num(e.exclusion_zone_distance_m);
      const seconds = num(e.exclusion_zone_seconds);
      if (metres === null && seconds === null) return null;
      const parts = [
        metres === null ? null : distance(metres),
        seconds === null ? null : duration(seconds),
      ].filter(Boolean);
      return `${parts.join(", ")} inside an excluded area`;
    },
  },
  {
    keys: ["total_match_count", "cross_account_match_count", "match_kind"],
    render: (e) => {
      const total = num(e.total_match_count);
      const others = num(e.cross_account_match_count);
      if (total === null) return null;
      const kind =
        e.match_kind === "identical"
          ? "; identical times"
          : e.match_kind === "time_shifted"
            ? "; same path at different times"
            : "";
      const byOthers = others ? ` (${whole.format(others)} by another driver)` : "";
      return `Same route as ${counted(total, "other trip", "other trips")}${byOthers}${kind}`;
    },
  },
];

function fallbackValue(value: unknown): string {
  let rendered: string;
  if (typeof value === "string") rendered = value;
  else if (typeof value === "number" || typeof value === "boolean") rendered = String(value);
  else {
    try {
      rendered = JSON.stringify(value) ?? "Unavailable";
    } catch {
      rendered = "Unavailable";
    }
  }
  return rendered.length > 120 ? `${rendered.slice(0, 117)}…` : rendered;
}

export function readableEvidence(evidence: Evidence | null | undefined): string[] {
  const remaining = Object.fromEntries(
    Object.entries(evidence ?? {}).filter(([key]) => !HIDDEN_KEYS.has(key)),
  );
  const lines = checkResult(remaining.result);
  delete remaining.result;
  for (const rule of RULES) {
    if (!rule.keys.some((key) => key in remaining)) continue;
    const line = rule.render(remaining);
    if (line === null) continue;
    lines.push(line);
    for (const key of rule.keys) delete remaining[key];
  }
  for (const [key, value] of Object.entries(remaining)) {
    const label = key.replaceAll("_", " ");
    lines.push(`${label.charAt(0).toUpperCase()}${label.slice(1)}: ${fallbackValue(value)}`);
  }
  return lines;
}
