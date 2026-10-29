import type { BudgetUsed } from "@/lib/api/audit-batch2";

type Campaign = {
  currency: string;
  budget_amount?: string | null;
  budget_used?: BudgetUsed | null;
};
/** Booked: one campaign's billing commitment (D103), never summed across campaigns or currencies. */
export type BudgetDisplay = {
  booked: bigint;
  /** The campaign's total budget; null when it has none (a daily-only campaign). */
  budget: bigint | null;
  currency: string;
  asOf: string;
};

export function moneyMinor(value: string | null | undefined): bigint | null {
  if (!value || !/^\d+(\.\d{1,2})?$/.test(value)) return null;
  const [whole, fraction = ""] = value.split(".");
  return BigInt(whole!) * BigInt(100) + BigInt(fraction.padEnd(2, "0"));
}
export function minorDecimal(value: bigint): string {
  return `${value / BigInt(100)}.${(value % BigInt(100)).toString().padStart(2, "0")}`;
}

/** The campaign's own booked figure, or null (shown as a dash) when missing or inconsistent. */
export function bookedBudget(campaign: Campaign): BudgetDisplay | null {
  const used = campaign.budget_used;
  if (!used) return null;
  const booked = moneyMinor(used.amount);
  const budget = used.budget_amount == null ? null : moneyMinor(used.budget_amount);
  if (
    booked === null ||
    (used.budget_amount != null && (budget === null || budget <= BigInt(0))) ||
    // The page also shows the campaign's budget; never show two different ones.
    budget !== (campaign.budget_amount ? moneyMinor(campaign.budget_amount) : null) ||
    used.currency !== campaign.currency ||
    !Number.isFinite(Date.parse(used.as_of))
  )
    return null;
  return { booked, budget, currency: used.currency, asOf: used.as_of };
}
