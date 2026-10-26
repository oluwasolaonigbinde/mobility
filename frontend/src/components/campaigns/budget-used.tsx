import { formatDateTime, formatMoney } from "@/lib/format";
import { bookedPercent, minorDecimal, type BudgetDisplay } from "@/lib/advertiser/budget-display";

export function BudgetUsed({ value }: { value: BudgetDisplay | null }) {
  if (!value)
    return (
      <h2 className="text-xl font-semibold">
        Booked: <span aria-hidden="true">—</span>
        <span className="sr-only">not available</span>
      </h2>
    );
  const booked = formatMoney(minorDecimal(value.booked), value.currency);
  const asOf = (
    <p className="text-muted mt-2 text-[15px]">
      As at {formatDateTime(value.asOf)} · Nigeria time (WAT)
    </p>
  );
  // A campaign with only a daily budget has no total to measure against.
  if (value.budget === null)
    return (
      <div>
        <h2 className="text-xl font-semibold">Booked: {booked}</h2>
        {asOf}
      </div>
    );
  const percent = bookedPercent(value.booked, value.budget);
  const budget = formatMoney(minorDecimal(value.budget), value.currency);
  // Exactly the budget is the normal full state once production starts; only more is a warning.
  const over = value.booked > value.budget;
  return (
    <div>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <h2 className="text-xl font-semibold">
          Booked: {booked}{" "}
          <span className="text-muted text-base font-normal">of your {budget} budget</span>
        </h2>
        <span className={`${over ? "text-amber" : "text-green"} text-sm font-semibold`}>
          {percent}%
        </span>
      </div>
      <progress
        aria-label="Budget booked"
        aria-valuetext={`${booked} of ${budget}; ${percent}%`}
        max={100}
        value={Math.min(percent, 100)}
        className={`${over ? "accent-amber [&::-webkit-progress-value]:bg-amber" : "accent-green [&::-webkit-progress-value]:bg-green"} [&::-webkit-progress-bar]:bg-raised mt-4 h-2 w-full overflow-hidden rounded-full`}
      />
      {asOf}
    </div>
  );
}
