import { formatDateTime, formatMoneyExact } from "@/lib/format";

// D38(c): drivers see every accepted term in words, without the IDs, hashes,
// map geometry or version markers that the frozen offer also carries. The
// daily-rate (payout_v4) pay values are shown as plain sentences instead
// (dailyRateSentences), so their raw keys are hidden here.
const HIDDEN_KEY =
  /(^id$|_id$|_ids$|sha256|fingerprint|checksum|hash|wkt|version|semantics|marker|^daily_rate_naira$|^daily_target_miles$|^shortfall_strategy$|^deduction_per_mile_naira$|^minimum_miles$|^outside_area_weight$)/;

function naira(value: unknown): string {
  return formatMoneyExact(String(value)).replace(/\.00$/, "");
}

function number(value: unknown): string {
  return String(Number(value));
}

/**
 * D39 daily-rate terms as the driver reads them. Every value comes from the
 * frozen offer; nothing is assumed. Returns [] for any other pay model.
 */
export function dailyRateSentences(terms: Record<string, unknown>): string[] {
  const payout = terms.payout as Record<string, unknown> | null | undefined;
  if (!payout || payout.formula_version !== "payout_v4") return [];
  const target = number(payout.daily_target_miles);
  const sentences = [
    `${naira(payout.daily_rate_naira)} for a full day of ${target} miles.`,
    `Driving more than ${target} miles in a day still earns ${naira(payout.daily_rate_naira)}.`,
    payout.shortfall_strategy === "per_mile_deduction"
      ? `Each mile short of ${target} takes ${naira(payout.deduction_per_mile_naira)} off the day's pay.`
      : "Shorter days are paid in proportion to the miles covered.",
  ];
  if (Number(payout.minimum_miles) > 0) {
    sentences.push(`Days under ${number(payout.minimum_miles)} miles are not paid.`);
  }
  const eligibility = terms.eligibility as Record<string, unknown> | null | undefined;
  const stopMinutes = Number(eligibility?.stationary_window_seconds) / 60;
  if (Number.isFinite(stopMinutes) && stopMinutes > 0) {
    sentences.push(
      `Stops of up to ${number(stopMinutes)} minutes count as driving; longer stops add no miles.`,
    );
  }
  const gapSeconds = Number(eligibility?.max_ping_gap_seconds);
  if (Number.isFinite(gapSeconds) && gapSeconds > 0) {
    sentences.push(
      `No miles are counted while your phone loses its location for more than ${
        gapSeconds % 60 === 0
          ? `${gapSeconds / 60} minute${gapSeconds === 60 ? "" : "s"}`
          : `${gapSeconds} seconds`
      }.`,
    );
  }
  const weight = Number(payout.outside_area_weight);
  sentences.push(
    weight >= 1
      ? "Miles outside the campaign area count in full."
      : weight <= 0
        ? "Only miles inside the campaign area count."
        : `Miles outside the campaign area count at ${number(Math.round(weight * 1000) / 10)}%.`,
  );
  return sentences;
}

export type OfferTermLine = { label: string; value: string };

function humanise(key: string): string {
  const words = key.replaceAll("_", " ").trim();
  return words.charAt(0).toUpperCase() + words.slice(1);
}

function scalar(value: unknown): string | null {
  if (value === null || value === undefined || value === "") return null;
  if (typeof value === "boolean") return value ? "Yes" : "No";
  if (typeof value === "string" && /^\d{4}-\d{2}-\d{2}T/.test(value)) return formatDateTime(value);
  if (typeof value === "string" || typeof value === "number") return String(value);
  return null;
}

export function offerTermLines(terms: Record<string, unknown>, prefix = ""): OfferTermLine[] {
  const lines: OfferTermLine[] = [];
  for (const [key, value] of Object.entries(terms)) {
    if (HIDDEN_KEY.test(key)) continue;
    const label = prefix ? `${prefix} · ${humanise(key)}` : humanise(key);
    if (Array.isArray(value)) {
      const names = value
        .map((item) =>
          item && typeof item === "object"
            ? scalar((item as Record<string, unknown>).name)
            : scalar(item),
        )
        .filter((item): item is string => item !== null);
      if (names.length) lines.push({ label, value: names.join(", ") });
    } else if (value && typeof value === "object") {
      lines.push(...offerTermLines(value as Record<string, unknown>, label));
    } else {
      const text = scalar(value);
      if (text !== null) lines.push({ label, value: text });
    }
  }
  return lines;
}
