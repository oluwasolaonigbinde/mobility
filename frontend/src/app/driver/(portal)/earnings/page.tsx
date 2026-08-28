import type { Metadata } from "next";
import Link from "next/link";
import { redirect } from "next/navigation";
import { createApiClient } from "@/lib/api/client";
import { getSessionToken } from "@/lib/auth/session";
import { formatDate, formatMoney, formatMoneyExact } from "@/lib/format";
import { Panel } from "@/components/ui/panel";
import { StatusChip } from "@/components/ui/status-chip";
import { DriverDataUnavailable } from "@/components/driver/data-unavailable";
import { FreshDriverAuthority } from "@/components/driver/fresh-authority";
import { readDriverApi } from "@/lib/driver/api-read";
import { activeHeldTripIds, presentLedgerEntry } from "@/lib/driver/earnings-presentation";

export const metadata: Metadata = { title: "Earnings" };

export default async function DriverEarningsPage() {
  const api = createApiClient(await getSessionToken());

  const [summary, ledger, assignments, holds] = await Promise.all([
    readDriverApi(() => api.GET("/api/v1/driver/earnings/summary")),
    readDriverApi(() =>
      api.GET("/api/v1/driver/earnings/ledger", { params: { query: { limit: 50 } } }),
    ),
    readDriverApi(() =>
      api.GET("/api/v1/driver/campaign-assignments", { params: { query: { limit: 50 } } }),
    ),
    readDriverApi(() => api.GET("/api/v1/driver/fraud-holds")),
  ]);

  if ([summary, ledger, assignments, holds].some((source) => source.state === "auth")) {
    redirect("/login");
  }
  if (
    summary.state !== "ready" ||
    ledger.state !== "ready" ||
    assignments.state !== "ready" ||
    holds.state !== "ready"
  ) {
    return (
      <div className="animate-rise flex flex-col gap-4">
        <h1 className="font-display text-2xl font-semibold tracking-tight">Earnings</h1>
        <DriverDataUnavailable
          title="Earnings and review status are unavailable"
          detail="Cardvert could not verify the current ledger, campaign history, or hold authority. No saved balance is shown as current."
          retryHref="/driver/earnings"
        />
      </div>
    );
  }

  const totals = summary.data.totals_by_currency;
  const entries = ledger.data.items;
  const campaignNames = new Map(
    assignments.data.items.map((item) => [item.campaign_id, item.campaign?.name ?? "Campaign"]),
  );
  const heldTripIds = activeHeldTripIds(holds.data.items);
  const presentedEntries = entries.map((entry) => ({
    entry,
    presentation: presentLedgerEntry(entry, heldTripIds),
  }));
  const heldEntries = presentedEntries.filter(
    ({ presentation }) => presentation.status.label === "Held",
  );
  const pendingEntries = presentedEntries.filter(
    ({ presentation }) => presentation.status.label === "Pending",
  );
  const releasedEntries = presentedEntries.filter(
    ({ presentation }) => presentation.status.label === "Released",
  );
  const paidEntries = presentedEntries.filter(
    ({ presentation }) => presentation.status.label === "Paid",
  );

  return (
    <FreshDriverAuthority
      title="Current earnings hidden while offline"
      detail="Reconnect to verify the latest balance, ledger and review status. Previously loaded money and hold details are not shown as current."
      retryHref="/driver/earnings"
    >
      <div className="animate-rise flex flex-col gap-4">
        <h1 className="font-display text-2xl font-semibold tracking-tight">Earnings</h1>

        {totals.map((t) => {
          const values = [
            ["Batch-payable", t.batch_payable_amount, "text-green"],
            ["Pending", t.pending_amount, "text-amber"],
            ["Released", t.released_available_amount, "text-green"],
            ["Available ledger", t.available_amount, "text-green"],
            ["Cash paid", t.cash_paid_amount, "text-green"],
            ["Paid ledger", t.paid_amount, "text-green"],
            ["Carried debt", t.carry_forward_debt_amount, "text-coral"],
            ["Voided", t.voided_amount, "text-faint"],
            ["Lifetime earned", t.lifetime_earned_amount, ""],
          ] as const;
          return (
            <div key={t.currency} className="grid grid-cols-2 gap-3">
              {values.map(([label, amount, tone]) => (
                <Panel key={label} className="p-4">
                  <p className="micro text-faint">{label}</p>
                  <p className={`font-display mt-1 text-lg font-semibold ${tone}`}>
                    {formatMoney(amount, t.currency)}
                  </p>
                </Panel>
              ))}
              <Panel className="p-4">
                <p className="micro text-faint">Ledger entries</p>
                <p className="font-display mt-1 text-lg font-semibold">{t.ledger_entry_count}</p>
              </Panel>
            </div>
          );
        })}

        <Panel className="p-5">
          <div className="flex items-start justify-between gap-4">
            <div>
              <p className="micro text-muted">Payout journey</p>
              <p className="mt-2 text-sm font-medium">
                Recent page: {heldEntries.length} held · {pendingEntries.length} other pending ·{" "}
                {releasedEntries.length} released · {paidEntries.length} paid
              </p>
              <p className="text-muted mt-1 text-xs leading-5">
                Open a trip below to see its verified time, rate, cap progress, exclusions, and
                ledger trail.
              </p>
            </div>
            <span className="bg-green/10 text-green flex size-10 shrink-0 items-center justify-center rounded-full font-mono">
              ₦
            </span>
          </div>
        </Panel>

        <Panel className="overflow-hidden">
          <div className="border-edge border-b px-5 py-3.5">
            <h2 className="micro text-muted">Ledger · every naira traced to a trip</h2>
            <p className="text-faint mt-1 text-xs">{entries.length} recent entries</p>
          </div>
          {entries.length === 0 ? (
            <p className="text-muted px-5 py-10 text-center text-sm">
              No entries yet — verified trips generate payouts here.
            </p>
          ) : (
            <ul className="divide-edge/60 divide-y">
              {presentedEntries.map(({ entry: e, presentation }) => {
                const row = (
                  <>
                    <div className="min-w-0">
                      <p className="truncate text-sm font-medium">
                        {campaignNames.get(e.campaign_id) ??
                          e.description ??
                          e.entry_type.replace("_", " ")}
                      </p>
                      <p className="micro text-faint mt-0.5">{formatDate(e.occurred_at)}</p>
                      {presentation.typeLabel ? (
                        <p className="micro text-muted mt-1">{presentation.typeLabel}</p>
                      ) : null}
                    </div>
                    <div className="flex shrink-0 items-center gap-2">
                      <span className="font-mono text-sm">
                        {e.entry_type === "reversal" ? "−" : ""}
                        {formatMoneyExact(e.amount, e.currency)}
                      </span>
                      <StatusChip tone={presentation.status.tone}>
                        {presentation.status.label}
                      </StatusChip>
                    </div>
                  </>
                );
                return (
                  <li key={e.id}>
                    {e.trip_session_id ? (
                      <Link
                        href={`/driver/earnings/trips/${e.trip_session_id}`}
                        className="hover:bg-raised/60 flex items-center justify-between gap-3 px-5 py-3.5 transition-colors"
                      >
                        {row}
                      </Link>
                    ) : (
                      <div className="flex items-center justify-between gap-3 px-5 py-3.5">
                        {row}
                      </div>
                    )}
                  </li>
                );
              })}
            </ul>
          )}
        </Panel>
      </div>
    </FreshDriverAuthority>
  );
}
