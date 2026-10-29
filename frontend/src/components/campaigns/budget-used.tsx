import { formatDateTime, formatMoney } from "@/lib/format";
import { minorDecimal, type BudgetDisplay } from "@/lib/advertiser/budget-display";

export function BudgetUsed({ value }: { value: BudgetDisplay | null }) {
  if (!value)
    return (
      <h2 className="text-xl font-semibold">
        Booked: <span aria-hidden="true">—</span>
        <span className="sr-only">not available</span>
      </h2>
    );
  return (
    <div>
      <h2 className="text-xl font-semibold">
        Booked: {formatMoney(minorDecimal(value.booked), value.currency)}
        {/* A campaign with only a daily budget has no total to show. */}
        {value.budget === null ? null : (
          <>
            {" "}
            <span className="text-muted text-base font-normal">
              of your {formatMoney(minorDecimal(value.budget), value.currency)} budget
            </span>
          </>
        )}
      </h2>
      <p className="text-muted mt-2 text-[15px]">
        As at {formatDateTime(value.asOf)} · Nigeria time (WAT)
      </p>
    </div>
  );
}
