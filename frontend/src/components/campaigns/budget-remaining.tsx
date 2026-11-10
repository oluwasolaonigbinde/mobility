import { remainingBudget, wholeMoney, type BudgetCampaign } from "@/lib/advertiser/budget-display";
import { campaignDay } from "@/lib/campaigns/day-progress";
export function BudgetRemaining({
  campaign,
  showDay = false,
}: {
  campaign: BudgetCampaign;
  showDay?: boolean;
}) {
  const value = remainingBudget(campaign),
    day = showDay ? campaignDay(campaign.start_at, campaign.end_at, campaign.status) : null;
  return (
    <div>
      <p className="font-display text-xl font-semibold">
        {wholeMoney(value.remaining, value.currency)}
      </p>
      <p className="text-muted text-sm">
        <span className="whitespace-nowrap">Budget {wholeMoney(value.budget, value.currency)}</span>
        {day ? ` · ${day}` : ""}
      </p>
    </div>
  );
}
