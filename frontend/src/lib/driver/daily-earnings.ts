import type { components } from "@/lib/api/schema";

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

/** Plain words for a day the server already totalled (REQ-208). */
export function presentEarningsDay(day: Day): EarningsDay {
  return {
    day: day.day,
    currency: day.currency,
    amount: day.amount,
    paidAt: day.paid_at,
    tripIds: day.trip_ids,
    status:
      day.status === "on_hold"
        ? "On hold – contact support"
        : day.status === "paid" && day.paid_at
          ? `Paid ${new Intl.DateTimeFormat("en-NG", { timeZone: "Africa/Lagos", day: "numeric", month: "short" }).format(new Date(day.paid_at))}`
          : day.status === "paying_tonight"
            ? "Paying tonight"
            : "Being checked",
  };
}
