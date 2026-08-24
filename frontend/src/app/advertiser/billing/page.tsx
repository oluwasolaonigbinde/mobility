import type { Metadata } from "next";
import Link from "next/link";
import { createApiClient } from "@/lib/api/client";
import { getSessionToken } from "@/lib/auth/session";
import { formatDate, formatMoney } from "@/lib/format";
import { PageHeader } from "@/components/ui/page-header";
import { Panel } from "@/components/ui/panel";
import { StatusChip } from "@/components/ui/status-chip";

export const metadata: Metadata = { title: "Billing history" };

export default async function AdvertiserBillingPage() {
  const api = createApiClient(await getSessionToken());
  const { data: history } = await api.GET("/api/v1/advertiser/billing");
  const rows = history ?? [];
  return (
    <div className="animate-rise mx-auto max-w-6xl">
      <PageHeader
        title="Billing history"
        eyebrow="Canonical receipts, lifecycle events and accepted-term allocations"
        actions={<Link href="/advertiser/company" className="border-edge bg-raised rounded-lg border px-4 py-2.5 text-sm">Billing details</Link>}
      />
      <Panel className="overflow-hidden">
        {rows.length ? (
          <ul className="divide-edge/60 divide-y">
            {rows.map((entry) => (
              <li key={entry.receipt.id} className="px-6 py-5">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <p className="font-mono text-sm">{entry.receipt.external_transaction_id}</p>
                    <p className="micro text-muted mt-1">{entry.receipt.payer_name} · {formatDate(entry.receipt.observed_at)}</p>
                  </div>
                  <div className="text-right">
                    <p className="font-mono text-sm">{formatMoney(entry.receipt.amount, entry.receipt.currency)}</p>
                    <StatusChip tone={entry.current_status === "confirmed" ? "green" : entry.current_status === "reversed" ? "coral" : "amber"}>{entry.current_status ?? "observed"}</StatusChip>
                  </div>
                </div>
                <p className="micro text-muted mt-3">
                  {entry.allocations.length
                    ? `${entry.allocations.length} immutable allocation${entry.allocations.length === 1 ? "" : "s"}`
                    : "Unapplied — does not authorize production"}
                </p>
              </li>
            ))}
          </ul>
        ) : <p className="text-muted px-6 py-12 text-center text-sm">No canonical receipts have been recorded.</p>}
      </Panel>
      <p className="micro text-muted mt-4">Online payment checkout is unavailable until an approved provider is configured. Manual bank-transfer evidence remains the canonical supported path.</p>
    </div>
  );
}
