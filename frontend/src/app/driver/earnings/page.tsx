import type { Metadata } from "next";
import { createApiClient } from "@/lib/api/client";
import { getSessionToken } from "@/lib/auth/session";
import { ApiError } from "@/lib/api/errors";
import { formatDate, formatMoney } from "@/lib/format";
import { Panel } from "@/components/ui/panel";
import { StatusChip } from "@/components/ui/status-chip";
import type { components } from "@/lib/api/schema";

export const metadata: Metadata = { title: "Earnings" };

type LedgerStatus = components["schemas"]["EarningsLedgerEntryStatus"];

const statusTone: Record<LedgerStatus, "green" | "amber" | "coral" | "default"> = {
  available: "green",
  pending: "amber",
  voided: "coral",
  reversed: "default",
};

export default async function DriverEarningsPage() {
  const api = createApiClient(await getSessionToken());

  const [summary, ledger] = await Promise.all([
    api.GET("/api/v1/driver/earnings/summary").catch((e) => {
      if (e instanceof ApiError && e.status === 404) return { data: undefined };
      throw e;
    }),
    api.GET("/api/v1/driver/earnings/ledger", { params: { query: { limit: 50 } } }).catch((e) => {
      if (e instanceof ApiError && e.status === 404) return { data: undefined };
      throw e;
    }),
  ]);

  const totals = summary.data?.totals_by_currency ?? [];
  const entries = ledger.data?.items ?? [];

  return (
    <div className="animate-rise flex flex-col gap-4">
      <h1 className="font-display text-2xl font-semibold tracking-tight">Earnings</h1>

      {totals.map((t) => (
        <div key={t.currency} className="grid grid-cols-3 gap-3">
          <Panel className="p-4">
            <p className="micro text-faint">Available</p>
            <p className="font-display text-green mt-1 text-lg font-semibold">
              {formatMoney(t.available_amount, t.currency)}
            </p>
          </Panel>
          <Panel className="p-4">
            <p className="micro text-faint">Pending</p>
            <p className="font-display text-amber mt-1 text-lg font-semibold">
              {formatMoney(t.pending_amount, t.currency)}
            </p>
          </Panel>
          <Panel className="p-4">
            <p className="micro text-faint">Lifetime</p>
            <p className="font-display mt-1 text-lg font-semibold">
              {formatMoney(t.lifetime_earned_amount, t.currency)}
            </p>
          </Panel>
        </div>
      ))}

      <Panel className="overflow-hidden">
        <div className="border-edge border-b px-5 py-3.5">
          <h2 className="micro text-muted">Ledger · every naira traced to a trip</h2>
        </div>
        {entries.length === 0 ? (
          <p className="text-muted px-5 py-10 text-center text-sm">
            No entries yet — verified trips generate payouts here.
          </p>
        ) : (
          <ul className="divide-edge/60 divide-y">
            {entries.map((e) => (
              <li key={e.id} className="flex items-center justify-between gap-3 px-5 py-3.5">
                <div className="min-w-0">
                  <p className="truncate text-sm">
                    {e.description ?? e.entry_type.replace("_", " ")}
                  </p>
                  <p className="micro text-faint mt-0.5">{formatDate(e.occurred_at)}</p>
                </div>
                <div className="flex shrink-0 items-center gap-2">
                  <span className="font-mono text-sm">{formatMoney(e.amount, e.currency)}</span>
                  <StatusChip tone={statusTone[e.status]}>{e.status}</StatusChip>
                </div>
              </li>
            ))}
          </ul>
        )}
      </Panel>
    </div>
  );
}
