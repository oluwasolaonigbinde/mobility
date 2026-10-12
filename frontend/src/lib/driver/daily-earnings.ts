import type { components } from "@/lib/api/schema";

type Entry = components["schemas"]["EarningsLedgerEntryRead"];
export type EarningsDay = {
  day: string;
  currency: string;
  amount: string;
  status: string;
  paidAt: string | null;
  tripIds: string[];
};
export const watDay = (date: Date) =>
  new Intl.DateTimeFormat("en-CA", {
    timeZone: "Africa/Lagos",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(date);

function cents(value: string | null): bigint | null {
  if (!value || !/^-?\d+(\.\d{1,2})?$/.test(value)) return null;
  const negative = value.startsWith("-");
  const [whole, fraction = ""] = value.replace(/^-/, "").split(".");
  const total = BigInt(whole!) * BigInt(100) + BigInt(fraction.padEnd(2, "0"));
  return negative ? -total : total;
}
const decimal = (value: bigint) =>
  `${value < BigInt(0) ? "-" : ""}${(value < BigInt(0) ? -value : value) / BigInt(100)}.${String((value < BigInt(0) ? -value : value) % BigInt(100)).padStart(2, "0")}`;

/** Complete ledger only: missing day allocations never become invented daily totals. */
export function dailyEarnings(entries: Entry[], heldTrips: Set<string>): EarningsDay[] | null {
  const groups = new Map<
    string,
    { amount: bigint; entries: Entry[]; day: string; currency: string }
  >();
  for (const entry of entries) {
    // Debt remainders record settlement provenance, not another earning.
    // A reversed original remains economic until its reversal entry nets it.
    if (entry.status === "voided" || entry.entry_type === "debt_remainder") continue;
    if (!entry.work_days?.length) return null;
    const allocations = entry.work_days.map((allocation) => cents(allocation.amount));
    if (
      allocations.some((amount) => amount === null) ||
      allocations.reduce<bigint>((sum, amount) => sum + (amount ?? BigInt(0)), BigInt(0)) !==
        cents(entry.amount)
    )
      return null;
    entry.work_days.forEach((allocation, index) => {
      const key = `${allocation.day}:${entry.currency}`;
      const group = groups.get(key) ?? {
        day: allocation.day,
        currency: entry.currency,
        amount: BigInt(0),
        entries: [],
      };
      group.amount += (entry.entry_type === "reversal" ? -1n : 1n) * allocations[index]!;
      if (allocations[index] !== BigInt(0)) group.entries.push(entry);
      groups.set(key, group);
    });
  }
  return [...groups.values()]
    .sort((a, b) => b.day.localeCompare(a.day) || a.currency.localeCompare(b.currency))
    .map((group) => {
      const held =
        group.amount < BigInt(0) ||
        group.entries.some(
          (entry) =>
            entry.payment_on_hold ||
            entry.status === "reversed" ||
            (entry.status === "paid" && !entry.paid_at) ||
            (entry.status !== "paid" &&
              entry.trip_session_id &&
              heldTrips.has(entry.trip_session_id)),
        );
      const paid =
        group.entries.length > 0 &&
        group.entries.every((entry) => entry.status === "paid" && entry.paid_at);
      const tonight =
        group.entries.length > 0 &&
        group.entries.every((entry) => entry.status === "available" && entry.paying_tonight);
      const paidDate = paid
        ? group.entries
            .map((entry) => entry.paid_at!)
            .sort()
            .at(-1)!
        : null;
      return {
        day: group.day,
        currency: group.currency,
        amount: decimal(group.amount),
        paidAt: !held ? paidDate : null,
        tripIds: [
          ...new Set(
            group.entries.flatMap((entry) =>
              entry.trip_session_id ? [entry.trip_session_id] : [],
            ),
          ),
        ],
        status: held
          ? "On hold – contact support"
          : paid
            ? `Paid ${new Intl.DateTimeFormat("en-NG", { timeZone: "Africa/Lagos", day: "numeric", month: "short" }).format(new Date(paidDate!))}`
            : tonight
              ? "Paying tonight"
              : "Being checked",
      };
    });
}
