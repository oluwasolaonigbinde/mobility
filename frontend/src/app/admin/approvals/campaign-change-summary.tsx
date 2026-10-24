import type { components } from "@/lib/api/schema";
import { formatDate, formatMoney } from "@/lib/format";

type Change = Pick<
  components["schemas"]["CampaignChangeRead"],
  "status" | "impact_preview" | "requested_liability_amount"
>;

function facts(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

export function CampaignChangeSummary({ change, currency }: { change: Change; currency: string }) {
  const before = facts(change.impact_preview.before);
  const after = facts(change.impact_preview.after);
  const reason = change.impact_preview.request_reason;
  return (
    <div className="mb-4 space-y-3 text-sm">
      {typeof reason === "string" && reason.trim() ? (
        <p>Advertiser&apos;s reason: {reason}</p>
      ) : null}
      <dl className="grid gap-3 sm:grid-cols-2">
        {(
          [
            ["start_at", "Start date"],
            ["end_at", "End date"],
            ["budget_amount", "Budget"],
            ["daily_budget_amount", "Daily budget"],
          ] as const
        ).map(([key, label]) => {
          const display = (value: unknown) =>
            value == null
              ? "Not set"
              : key.endsWith("_at")
                ? formatDate(String(value))
                : formatMoney(String(value), currency);
          return (
            <div key={key}>
              <dt className="micro text-muted">{label}</dt>
              <dd>
                {display(before[key])} → {display(after[key])}
              </dd>
            </div>
          );
        })}
        <div>
          <dt className="micro text-muted">Funding needed</dt>
          <dd>
            {formatMoney(change.requested_liability_amount, currency)}
            {change.status === "pending_funding" ||
            change.impact_preview.outcome === "await_funding"
              ? " · Waiting for funding"
              : ""}
          </dd>
        </div>
      </dl>
    </div>
  );
}
