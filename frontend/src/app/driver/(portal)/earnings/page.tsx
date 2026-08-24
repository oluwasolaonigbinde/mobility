import type { Metadata } from "next";
import Link from "next/link";
import { createApiClient } from "@/lib/api/client";
import { getSessionToken } from "@/lib/auth/session";
import { ApiError } from "@/lib/api/errors";
import { formatDate, formatMoney, formatMoneyExact } from "@/lib/format";
import { Panel } from "@/components/ui/panel";
import { StatusChip } from "@/components/ui/status-chip";
import type { components } from "@/lib/api/schema";

export const metadata: Metadata = { title: "Earnings" };

type LedgerStatus = components["schemas"]["EarningsLedgerEntryStatus"];

const statusTone: Record<LedgerStatus, "green" | "amber" | "coral" | "default"> = {
  available: "green",
  paid: "green",
  pending: "amber",
  voided: "coral",
  reversed: "default",
};

export default async function DriverEarningsPage() {
  const api = createApiClient(await getSessionToken());

  const [summary, ledger, assignments] = await Promise.all([
    api.GET("/api/v1/driver/earnings/summary").catch((e) => {
      if (e instanceof ApiError && e.status === 404) return { data: undefined };
      throw e;
    }),
    api.GET("/api/v1/driver/earnings/ledger", { params: { query: { limit: 50 } } }).catch((e) => {
      if (e instanceof ApiError && e.status === 404) return { data: undefined };
      throw e;
    }),
    api
      .GET("/api/v1/driver/campaign-assignments", { params: { query: { limit: 50 } } })
      .catch((e) => {
        if (e instanceof ApiError && e.status === 404) return { data: undefined };
        throw e;
      }),
  ]);

  const totals = summary.data?.totals_by_currency ?? [];
  const entries = ledger.data?.items ?? [];
  const campaignNames = new Map(
    (assignments.data?.items ?? []).map((item) => [
      item.campaign_id,
      item.campaign?.name ?? "Campaign",
    ]),
  );
  const availableEntries = entries.filter((entry) => entry.status === "available").length;
  const pendingEntries = entries.filter((entry) => entry.status === "pending").length;

  return (
    <div className="animate-rise flex flex-col gap-4">
      <h1 className="font-display text-2xl font-semibold tracking-tight">Earnings</h1>

      {totals.map((t) => (
        <div key={t.currency} className="grid grid-cols-2 gap-3">
          <Panel className="p-4">
            <p className="micro text-faint">Batch-payable</p>
            <p className="font-display text-green mt-1 text-lg font-semibold">
              {formatMoney(t.batch_payable_amount, t.currency)}
            </p>
          </Panel>
          <Panel className="p-4">
            <p className="micro text-faint">Pending</p>
            <p className="font-display text-amber mt-1 text-lg font-semibold">
              {formatMoney(t.pending_amount, t.currency)}
            </p>
          </Panel>
          <Panel className="p-4">
            <p className="micro text-faint">Carried debt</p>
            <p className="font-display mt-1 text-lg font-semibold">
              {formatMoney(t.carry_forward_debt_amount, t.currency)}
            </p>
          </Panel>
          <Panel className="p-4">
            <p className="micro text-faint">Lifetime earned</p>
            <p className="font-display mt-1 text-lg font-semibold">
              {formatMoney(t.lifetime_earned_amount, t.currency)}
            </p>
          </Panel>
        </div>
      ))}

      <Panel className="p-5">
        <div className="flex items-start justify-between gap-4">
          <div>
            <p className="micro text-muted">Payout journey</p>
            <p className="mt-2 text-sm font-medium">
              {availableEntries} available · {pendingEntries} pending
            </p>
            <p className="text-muted mt-1 text-xs leading-5">
              Open a trip below to see its verified time, rate, cap progress, exclusions, and ledger
              trail.
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
            {entries.map((e) => {
              const row = (
                <>
                  <div className="min-w-0">
                    <p className="truncate text-sm font-medium">
                      {campaignNames.get(e.campaign_id) ??
                        e.description ??
                        e.entry_type.replace("_", " ")}
                    </p>
                    <p className="micro text-faint mt-0.5">{formatDate(e.occurred_at)}</p>
                  </div>
                  <div className="flex shrink-0 items-center gap-2">
                    <span className="font-mono text-sm">
                      {e.entry_type === "reversal" ? "−" : ""}
                      {formatMoneyExact(e.amount, e.currency)}
                    </span>
                    <StatusChip tone={statusTone[e.status]}>{e.status}</StatusChip>
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
                    <div className="flex items-center justify-between gap-3 px-5 py-3.5">{row}</div>
                  )}
                </li>
              );
            })}
          </ul>
        )}
      </Panel>
    </div>
  );
}
