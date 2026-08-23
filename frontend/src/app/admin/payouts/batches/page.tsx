import type { Metadata } from "next";
import Link from "next/link";
import { PageHeader } from "@/components/ui/page-header";
import { Panel } from "@/components/ui/panel";
import { StatusChip } from "@/components/ui/status-chip";
import { formatDate, formatMoneyExact } from "@/lib/format";
import { batchApi, type PayoutBatch } from "./batch-api";
import { BatchActions, CreateBatchForm, PollLineAction } from "./batch-forms";

export const metadata: Metadata = { title: "Payout batches" };

export default async function PayoutBatchesPage() {
  const data = await batchApi<{ items: PayoutBatch[]; total: number }>("?limit=100&offset=0");
  return (
    <div className="animate-rise mx-auto max-w-6xl pb-16">
      <nav aria-label="Breadcrumb" className="micro text-faint mb-4">
        <Link href="/admin/payouts">Payouts</Link> / <span className="text-muted">Batches</span>
      </nav>
      <PageHeader
        title="Payout batches"
        eyebrow={`${data.total} batch${data.total === 1 ? "" : "es"} — frozen instructions require independent approval`}
      />
      <Panel className="mb-6 p-6">
        <h2 className="micro text-muted mb-3">Reserve available earnings</h2>
        <CreateBatchForm />
      </Panel>
      <Panel className="overflow-hidden">
        <table className="w-full min-w-[760px] text-sm">
          <thead>
            <tr className="border-edge micro text-muted border-b text-left">
              <th className="px-6 py-3 font-normal">Status</th>
              <th className="px-4 py-3 text-right font-normal">Total</th>
              <th className="px-4 py-3 font-normal">Maker</th>
              <th className="px-4 py-3 font-normal">Checker</th>
              <th className="px-4 py-3 font-normal">Created</th>
              <th className="px-4 py-3 font-normal">Lines</th>
              <th className="px-6 py-3 text-right font-normal">Actions</th>
            </tr>
          </thead>
          <tbody>
            {data.items.length ? (
              data.items.map((batch) => (
                <tr key={batch.id} className="border-edge/60 border-b last:border-0">
                  <td className="px-6 py-3">
                    <StatusChip>{batch.status}</StatusChip>
                  </td>
                  <td className="px-4 py-3 text-right font-mono text-xs">
                    {formatMoneyExact(batch.total_amount, batch.currency)}
                  </td>
                  <td className="text-muted px-4 py-3 font-mono text-xs">
                    {batch.created_by_user_id.slice(0, 8)}…
                  </td>
                  <td className="text-muted px-4 py-3 font-mono text-xs">
                    {batch.approved_by_user_id ? `${batch.approved_by_user_id.slice(0, 8)}…` : "—"}
                  </td>
                  <td className="text-muted px-4 py-3">{formatDate(batch.created_at)}</td>
                  <td className="px-4 py-3 text-xs">
                    {batch.lines.map((line) => (
                      <div key={line.id} className="mb-2 last:mb-0">
                        <span className="font-mono">{line.id.slice(0, 8)}…</span>{" "}
                        <StatusChip>{line.status}</StatusChip>
                        {line.status === "submitted" || line.status === "failed" ? (
                          <PollLineAction lineId={line.id} />
                        ) : null}
                      </div>
                    ))}
                  </td>
                  <td className="px-6 py-3">
                    {batch.status === "reserved" ||
                    batch.status === "reconciled" ||
                    batch.status === "failed" ? (
                      <BatchActions batchId={batch.id} status={batch.status} />
                    ) : null}
                  </td>
                </tr>
              ))
            ) : (
              <tr>
                <td colSpan={7} className="text-muted px-6 py-10 text-center">
                  No payout batches yet.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </Panel>
    </div>
  );
}
