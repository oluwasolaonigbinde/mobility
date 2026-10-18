import { formatDateTime, formatMoney } from "@/lib/format";
import { minorDecimal, type BudgetDisplay } from "@/lib/advertiser/budget-display";

export function BudgetUsed({ value }: { value: BudgetDisplay | null }) {
  if (!value)
    return (
      <div>
        <h2 className="font-semibold">Spent so far of your budget</h2>
        <p className="text-muted mt-2 text-sm">Spending is being updated.</p>
      </div>
    );
  const percent = Number((value.spent * BigInt(10000)) / value.budget) / 100;
  const spent = formatMoney(minorDecimal(value.spent), value.currency);
  const budget = formatMoney(minorDecimal(value.budget), value.currency);
  return (
    <div>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-muted text-sm font-medium">Spent so far of your budget</h2>
          <p className="mt-2 text-xl font-semibold">
            {spent} <span className="text-muted text-sm font-normal">of {budget}</span>
          </p>
        </div>
        <span className="text-green text-sm font-semibold">{percent}% used</span>
      </div>
      <progress
        aria-label="Budget used"
        aria-valuetext={`${spent} of ${budget}; ${percent}% used`}
        max={100}
        value={Math.min(percent, 100)}
        className="accent-green [&::-webkit-progress-bar]:bg-raised [&::-webkit-progress-value]:bg-green mt-4 h-2 w-full overflow-hidden rounded-full"
      />
      <p className="text-muted mt-2 text-xs">
        As at {formatDateTime(value.evaluatedAt)} · Nigeria time (WAT)
      </p>
    </div>
  );
}
