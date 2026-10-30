import type { components } from "@/lib/api/schema";
import { formatMoneyExact } from "@/lib/format";

type Day = components["schemas"]["DriverEarningsDayRead"];
export type EarningsTotals = components["schemas"]["DriverEarningsTotalsRead"];
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

/** The remaining recovery, computed by the server. */
export const overpaidNote = (money: string) => `${money} to be deducted`;

/** "₦10,000.00 paid · ₦100.00 to be deducted" for a trip paid before a deduction. */
export function paidBeforeDeduction(cash: string, toDeduct: string, currency: string) {
  return `${formatMoneyExact(cash, currency)} paid · ${overpaidNote(
    formatMoneyExact(toDeduct, currency),
  )}`;
}

/** Plain words for a day the server already totalled (REQ-208). */
export function presentEarningsDay(day: Day): EarningsDay {
  const status =
    day.status === "on_hold"
      ? "On hold – contact support"
      : day.status === "paid" && day.paid_at
        ? `Paid ${new Intl.DateTimeFormat("en-NG", { timeZone: "Africa/Lagos", day: "numeric", month: "short" }).format(new Date(day.paid_at))}`
        : day.status === "paying_tonight"
          ? "Paying tonight"
          : "Being checked";
  const toDeduct = day.to_deduct ?? "0.00";
  const base = {
    day: day.day,
    currency: day.currency,
    paidAt: day.paid_at,
    tripIds: day.trip_ids,
  };
  if (!(Number(toDeduct) > 0)) return { ...base, amount: day.amount, status };
  const note = overpaidNote(formatMoneyExact(toDeduct, day.currency));
  const beforeDeduction = day.cash_paid ?? "0.00";
  // A deduction on a day with no pay of its own: the deduction alone, no "₦0".
  if (!(Number(beforeDeduction) > 0)) return { ...base, amount: day.amount, status: note };
  // The day shows the cash that went out; the deduction is still to come.
  return { ...base, amount: beforeDeduction, status: `${status} · ${note}` };
}
