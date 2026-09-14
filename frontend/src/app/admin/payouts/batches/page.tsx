import type { Metadata } from "next";
import Link from "next/link";
import { PageHeader } from "@/components/ui/page-header";
import { Panel } from "@/components/ui/panel";
import { StatusChip } from "@/components/ui/status-chip";
import { requireRole } from "@/lib/auth/current-user";
import { formatDateTime, formatMoneyExact } from "@/lib/format";
import { batchApi } from "./batch-api";
import { CreateBatchForm } from "./batch-forms";
import {
  outcomeLabel,
  type BatchSummary,
  type EligiblePayment,
  type Page,
} from "./operation-types";

export const metadata: Metadata = { title: "Payout batches" };

export default async function PayoutBatchesPage({
  searchParams,
}: {
  searchParams: Promise<{
    q?: string;
    currency?: string;
    credits?: string;
    batches?: string;
    status?: string;
  }>;
}) {
  const me = await requireRole("admin");
  const query = await searchParams;
  const index = (value?: string) =>
    /^\d+$/.test(value ?? "") ? Math.min(Number(value), 100000) : 0;
  const credits = index(query.credits),
    batches = index(query.batches);
  const filters = new URLSearchParams({ limit: "25", offset: String(credits * 25) });
  if (query.q) filters.set("search", query.q.slice(0, 100));
  if (query.currency && /^[a-z]{3}$/i.test(query.currency))
    filters.set("currency", query.currency.toUpperCase());
  const batchFilters = new URLSearchParams({ limit: "25", offset: String(batches * 25) });
  if (query.status) batchFilters.set("batch_status", query.status);
  const [entries, summary] = await Promise.all([
    batchApi<Page<EligiblePayment>>(`/eligible?${filters}`),
    batchApi<Page<BatchSummary>>(`/summaries?${batchFilters}`),
  ]);
  const href = (kind: "credits" | "batches", page: number) => {
    const next = new URLSearchParams(
      Object.entries(query).filter((row): row is [string, string] => typeof row[1] === "string"),
    );
    next.set(kind, String(page));
    return `/admin/payouts/batches?${next}`;
  };
  return (
    <div className="animate-rise mx-auto max-w-6xl space-y-6 pb-16">
      <nav aria-label="Breadcrumb" className="micro text-muted">
        <Link href="/admin/payouts">Payouts</Link> / Batches
      </nav>
      <PageHeader
        title="Payout batches"
        eyebrow="Select credits, review frozen instructions, then obtain independent approval"
      />
      <Panel className="space-y-4 p-4 sm:p-6">
        <h2 className="font-display text-xl">Available earnings</h2>
        <form className="flex flex-wrap gap-3">
          <input
            aria-label="Search driver or campaign"
            name="q"
            defaultValue={query.q}
            placeholder="Driver or campaign name"
            maxLength={100}
            className="border-edge bg-raised min-w-0 flex-1 rounded-lg border px-3 py-2"
          />
          <input
            aria-label="Filter currency"
            name="currency"
            defaultValue={query.currency}
            placeholder="Currency"
            maxLength={3}
            className="border-edge bg-raised w-24 rounded-lg border px-3 py-2 uppercase"
          />
          <button className="border-edge rounded-lg border px-4 py-2">Search credits</button>
        </form>
        <CreateBatchForm
          key={`${credits}:${query.q}:${query.currency}`}
          entries={entries.items}
          actorId={me.user.id}
        />
        <nav aria-label="Credit pages" className="flex flex-wrap gap-4 text-sm">
          {credits > 0 ? <Link href={href("credits", credits - 1)}>Previous credits</Link> : null}
          <span>
            {entries.total} available credit records · page {credits + 1}
          </span>
          {(credits + 1) * 25 < entries.total ? (
            <Link href={href("credits", credits + 1)}>Next credits</Link>
          ) : null}
        </nav>
      </Panel>
      <Panel className="space-y-4 p-4 sm:p-6">
        <h2 className="font-display text-xl">Batch history</h2>
        <p className="text-muted text-sm">
          Queued work has not been submitted. Only verified success on an individual line records
          payment. Live transfers remain gated on an approved provider.
        </p>
        <form className="flex flex-wrap gap-3">
          <select
            name="status"
            aria-label="Batch status"
            defaultValue={query.status ?? ""}
            className="border-edge bg-raised rounded-lg border px-3 py-2"
          >
            <option value="">All statuses</option>
            {["draft", "reserved", "submitted", "reconciled", "completed", "failed", "void"].map(
              (status) => (
                <option key={status}>{status}</option>
              ),
            )}
          </select>
          <button className="border-edge rounded-lg border px-4 py-2">Filter batches</button>
        </form>
        <div className="grid gap-3 md:grid-cols-2">
          {summary.items.map((batch) => (
            <article key={batch.id} className="border-edge min-w-0 space-y-2 rounded-xl border p-4">
              <div className="flex flex-wrap justify-between gap-2">
                <StatusChip>{batch.status}</StatusChip>
                <strong>{formatMoneyExact(batch.total_amount, batch.currency)}</strong>
              </div>
              <p className="break-words">Maker: {batch.maker_name}</p>
              <p className="break-words">
                Checker: {batch.checker_name ?? "Awaiting independent approval"}
              </p>
              <p className="text-muted text-sm">
                {formatDateTime(batch.created_at)} · {batch.line_count} lines
              </p>
              {Object.entries(batch.outcomes).map(([outcome, count]) => (
                <p key={outcome} className="text-sm">
                  {outcomeLabel(outcome)}: {count}
                </p>
              ))}
              <Link className="inline-block underline" href={`/admin/payouts/batches/${batch.id}`}>
                Review batch
              </Link>
            </article>
          ))}
        </div>
        {!summary.items.length ? <p className="text-muted">No batches match this page.</p> : null}
        <nav aria-label="Batch pages" className="flex flex-wrap gap-4 text-sm">
          {batches > 0 ? <Link href={href("batches", batches - 1)}>Previous batches</Link> : null}
          <span>
            {summary.total} batches · page {batches + 1}
          </span>
          {(batches + 1) * 25 < summary.total ? (
            <Link href={href("batches", batches + 1)}>Next batches</Link>
          ) : null}
        </nav>
      </Panel>
    </div>
  );
}
