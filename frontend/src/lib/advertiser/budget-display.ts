import { campaignDayProgress } from "@/lib/campaigns/day-progress";
export type BudgetCampaign = {
  currency: string;
  budget_amount?: string | null;
  start_at?: string | null;
  end_at?: string | null;
  status: string;
  pause_kind?: string | null;
};
export function moneyMinor(value: string | null | undefined): bigint | null {
  if (typeof value !== "string" || !value || !/^\d+(\.\d{1,2})?$/.test(value)) return null;
  const [whole, fraction = ""] = value.split(".");
  return BigInt(whole!) * 100n + BigInt(fraction.padEnd(2, "0"));
}
export function minorDecimal(value: bigint): string {
  return `${value / 100n}.${(value % 100n).toString().padStart(2, "0")}`;
}
export function wholeMoney(value: bigint | null, currency: string): string {
  if (value === null) return "—";
  try {
    return new Intl.NumberFormat("en-NG", {
      style: "currency",
      currency,
      maximumFractionDigits: 0,
      minimumFractionDigits: 0,
    }).format(value / 100n);
  } catch {
    return "—";
  }
}
/** Display only. Billing, warnings, invoices and pay never use this countdown. */
export function remainingBudget(c: BudgetCampaign, now = new Date()) {
  const budget = moneyMinor(c.budget_amount);
  let remaining: bigint | null = null;
  if (
    !/^[A-Z]{3}$/.test(c.currency) ||
    budget === null ||
    budget <= 0n ||
    !Number.isFinite(now.getTime())
  )
    return { budget: null, remaining, currency: c.currency };
  if (c.status === "cancelled" || c.pause_kind === "budget")
    return { budget, remaining, currency: c.currency };
  if (c.status === "finished") remaining = 0n;
  else if (
    ["draft", "pending_review", "approved", "rejected"].includes(c.status) ||
    (["active", "paused"].includes(c.status) && (!c.start_at || !c.end_at))
  )
    remaining = budget;
  else if (["active", "paused"].includes(c.status)) {
    const progress = campaignDayProgress(c.start_at!, c.end_at!, now);
    if (progress)
      remaining =
        (budget * BigInt(progress.duration - progress.elapsed)) / BigInt(progress.duration);
  }
  return { budget, remaining, currency: c.currency };
}
export function campaignBudgets(campaigns: BudgetCampaign[], now = new Date()) {
  const totals = new Map<string, { budget: bigint | null; remaining: bigint | null }>();
  for (const c of campaigns) {
    if (c.budget_amount == null || moneyMinor(c.budget_amount) === 0n) continue;
    const value = remainingBudget(c, now),
      previous = totals.get(c.currency) ?? { budget: 0n, remaining: 0n };
    totals.set(c.currency, {
      budget:
        previous.budget === null || value.budget === null ? null : previous.budget + value.budget,
      remaining:
        previous.remaining === null || value.remaining === null
          ? null
          : previous.remaining + value.remaining,
    });
  }
  return [...totals].map(([currency, value]) => ({ currency, ...value }));
}
