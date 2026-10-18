import type { components } from "@/lib/api/schema";

type Campaign = Pick<components["schemas"]["CampaignRead"], "id" | "currency" | "budget_amount">;
type Evaluation = components["schemas"]["BudgetEvaluationRead"];
export type BudgetDisplay = {
  spent: bigint;
  budget: bigint;
  currency: string;
  evaluatedAt: string;
};

export function moneyMinor(value: string | null | undefined): bigint | null {
  if (!value || !/^\d+(\.\d{1,2})?$/.test(value)) return null;
  const [whole, fraction = ""] = value.split(".");
  return BigInt(whole!) * BigInt(100) + BigInt(fraction.padEnd(2, "0"));
}
export function minorDecimal(value: bigint): string {
  return `${value / BigInt(100)}.${(value % BigInt(100)).toString().padStart(2, "0")}`;
}

/** A daily or obsolete evaluation is never presented as total campaign spending. */
export function recordedBudget(
  campaign: Campaign,
  evaluations: Evaluation[] | undefined,
): BudgetDisplay | null {
  if (!evaluations?.length || evaluations.some((e) => !Number.isFinite(Date.parse(e.evaluated_at))))
    return null;
  const evaluation = [...evaluations].sort(
    (a, b) => Date.parse(b.evaluated_at) - Date.parse(a.evaluated_at),
  )[0]!;
  const budget = moneyMinor(campaign.budget_amount);
  const spent = moneyMinor(evaluation.billing_spend_amount);
  if (
    evaluation.budget_basis !== "total" ||
    !["within_budget", "alert_threshold", "urgent_threshold", "pause_threshold"].includes(
      evaluation.state,
    ) ||
    evaluation.external_gate ||
    evaluation.campaign_id !== campaign.id ||
    evaluation.currency !== campaign.currency ||
    moneyMinor(evaluation.campaign_budget_amount) !== budget ||
    budget === null ||
    budget <= BigInt(0) ||
    spent === null
  )
    return null;
  return { spent, budget, currency: campaign.currency, evaluatedAt: evaluation.evaluated_at };
}

export function combineBudgets(values: Array<BudgetDisplay | null>): BudgetDisplay | null {
  const first = values[0];
  if (!first || values.some((value) => !value || value.currency !== first.currency)) return null;
  return (values as BudgetDisplay[]).reduce(
    (total, value) => ({
      spent: total.spent + value.spent,
      budget: total.budget + value.budget,
      currency: first.currency,
      evaluatedAt:
        Date.parse(value.evaluatedAt) < Date.parse(total.evaluatedAt)
          ? value.evaluatedAt
          : total.evaluatedAt,
    }),
    {
      spent: BigInt(0),
      budget: BigInt(0),
      currency: first.currency,
      evaluatedAt: first.evaluatedAt,
    },
  );
}
