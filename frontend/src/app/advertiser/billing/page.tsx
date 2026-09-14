import type { Metadata } from "next";
import Link from "next/link";
import { createApiClient } from "@/lib/api/client";
import { getSessionToken } from "@/lib/auth/session";
import { formatDate, formatMoney } from "@/lib/format";
import { PageHeader } from "@/components/ui/page-header";
import { Panel } from "@/components/ui/panel";
import { StatusChip } from "@/components/ui/status-chip";
import { CommercialHistory } from "@/lib/billing/commercial-history";

export const metadata: Metadata = { title: "Billing history" };

const receiptStatusLabel: Record<string, string> = {
  observed: "Recorded – being checked",
  reconciled: "Amount matched – awaiting confirmation",
  confirmed: "Confirmed",
  reversed: "Reversed",
};

export default async function AdvertiserBillingPage() {
  const api = createApiClient(await getSessionToken());
  const [{ data: history }, { data: campaigns }] = await Promise.all([
    api.GET("/api/v1/advertiser/billing"),
    api.GET("/api/v1/advertiser/campaigns", {
      params: { query: { limit: 100, offset: 0 } },
    }),
  ]);
  const rows = history ?? [];
  const commercialHistory = await Promise.all(
    (campaigns?.items ?? []).map(async (campaign) => {
      const { data: commercial } = await api.GET(
        "/api/v1/advertiser/campaigns/{campaign_id}/commercial",
        { params: { path: { campaign_id: campaign.id } } },
      );
      return { campaign, commercial };
    }),
  );
  return (
    <div className="animate-rise mx-auto max-w-6xl">
      <PageHeader
        title="Billing history"
        eyebrow="Payments recorded for your campaigns and how they were applied"
        actions={
          <Link
            href="/advertiser/company"
            className="border-edge bg-raised rounded-lg border px-4 py-2.5 text-sm"
          >
            Billing details
          </Link>
        }
      />
      <Panel className="overflow-hidden">
        {rows.length ? (
          <ul className="divide-edge/60 divide-y">
            {rows.map((entry) => (
              <li key={entry.receipt.id} className="px-6 py-5">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <p className="font-mono text-sm">{entry.receipt.external_transaction_id}</p>
                    <p className="micro text-muted mt-1">
                      {entry.receipt.payer_name} · {formatDate(entry.receipt.observed_at)}
                    </p>
                  </div>
                  <div className="text-right">
                    <p className="font-mono text-sm">
                      {formatMoney(entry.receipt.amount, entry.receipt.currency)}
                    </p>
                    <StatusChip
                      tone={
                        entry.current_status === "confirmed"
                          ? "green"
                          : entry.current_status === "reversed"
                            ? "coral"
                            : "amber"
                      }
                    >
                      {receiptStatusLabel[entry.current_status ?? "observed"] ??
                        entry.current_status}
                    </StatusChip>
                  </div>
                </div>
                <p className="micro text-muted mt-3">
                  {entry.current_status === "reversed"
                    ? "Reversed – this payment no longer counts toward your campaign terms."
                    : entry.allocations.length
                      ? `Applied to your accepted campaign terms (${entry.allocations.length} allocation${entry.allocations.length === 1 ? "" : "s"})`
                      : "Not yet applied – production cannot start from this payment."}
                </p>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-muted px-6 py-12 text-center text-sm">
            No payments have been recorded yet.
          </p>
        )}
      </Panel>
      {commercialHistory.map(({ campaign, commercial }) =>
        commercial ? (
          <CommercialHistory
            key={campaign.id}
            campaign={{ id: campaign.id, name: campaign.name }}
            invoices={commercial.invoices}
            settlements={commercial.settlements}
          />
        ) : null,
      )}
      <p className="micro text-muted mt-4">
        Online payment isn&apos;t available yet. Please pay by bank transfer.
      </p>
    </div>
  );
}
