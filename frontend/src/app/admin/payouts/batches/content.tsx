import { adminValueFailure } from "@/lib/api/admin-read";
import Link from "next/link";
import { Panel } from "@/components/ui/panel";
import { requireRole } from "@/lib/auth/current-user";
import { formatDateTime, formatMoneyExact } from "@/lib/format";
import { adminStatus } from "@/lib/status/admin";
import { QueueUnavailable } from "../../queue-search";
import { FilterChips } from "@/components/ui/tabs";
import { moneyHref, moneyPage, type MoneyQuery } from "../../money/navigation";
import { batchApi } from "./batch-api";
import { CreateBatchForm } from "./batch-forms";
import { EarningsSearch } from "./earnings-search";
import {
  outcomeLabel,
  type BatchSummary,
  type EligiblePayment,
  type Page,
} from "./operation-types";
export default async function PaymentRuns({ searchParams }: { searchParams: Promise<MoneyQuery> }) {
  const me = await requireRole("admin"),
    query = await searchParams;
  const credits = moneyPage(query.credits),
    runs = moneyPage(query.runs);
  const filters = new URLSearchParams({ limit: "25", offset: String(credits * 25) });
  if (query.q) filters.set("search", query.q.slice(0, 100));
  if (query.currency && /^[a-z]{3}$/i.test(query.currency))
    filters.set("currency", query.currency.toUpperCase());
  const runFilters = new URLSearchParams({ limit: "25", offset: String(runs * 25) });
  const statuses = ["draft", "reserved", "submitted", "reconciled", "completed", "failed", "void"];
  const runStatus = query.status && statuses.includes(query.status) ? query.status : undefined;
  if (runStatus) runFilters.set("batch_status", runStatus);
  const [entries, summary] = await Promise.all([
    batchApi<Page<EligiblePayment>>(`/eligible?${filters}`).catch(adminValueFailure),
    batchApi<Page<BatchSummary>>(`/summaries?${runFilters}`).catch(adminValueFailure),
  ]);
  return (
    <div className="space-y-6">
      <Panel className="space-y-4 p-4 sm:p-6">
        <h2 className="font-display text-xl">Available earnings</h2>
        <EarningsSearch query={query} />
        {!entries ? (
          <QueueUnavailable />
        ) : (
          <>
            <CreateBatchForm
              key={`${credits}:${query.q}:${query.currency}`}
              query={query}
              entries={entries.items}
              actorId={me.user.id}
            />
            <nav aria-label="Earnings pages" className="flex flex-wrap gap-4 text-sm">
              {credits > 0 ? (
                <Link href={moneyHref(query, { credits: String(credits - 1) })}>
                  Previous earnings
                </Link>
              ) : null}
              <span>
                {entries.total} available earnings records · page {credits + 1}
              </span>
              {(credits + 1) * 25 < entries.total ? (
                <Link href={moneyHref(query, { credits: String(credits + 1) })}>Next earnings</Link>
              ) : null}
            </nav>
          </>
        )}
      </Panel>
      <Panel className="space-y-4 p-4 sm:p-6">
        <h2 className="font-display text-xl">Payment runs</h2>
        <p className="text-muted text-sm">
          Waiting payments have not been submitted. A payment is recorded only after verified
          provider success.
        </p>
        <FilterChips
          label="Payment run status"
          items={[
            {
              href: moneyHref(query, { status: undefined, runs: undefined }),
              label: "All statuses",
              active: !runStatus,
            },
            ...statuses.map((status) => ({
              href: moneyHref(query, { status, runs: undefined }),
              label: adminStatus(status, "payment_run"),
              active: runStatus === status,
            })),
          ]}
        />
        {!summary ? (
          <QueueUnavailable />
        ) : (
          <>
            <div className="grid gap-3 md:grid-cols-2">
              {summary.items.map((run) => (
                <article
                  key={run.id}
                  className="border-edge min-w-0 space-y-2 rounded-xl border p-4"
                >
                  <p>
                    {adminStatus(run.status, "payment_run")} ·{" "}
                    <strong>{formatMoneyExact(run.total_amount, run.currency)}</strong>
                  </p>
                  {run.approval_mode === "automatic" ? (
                    <p>Approved automatically by Cardvert</p>
                  ) : (
                    <>
                      <p>Prepared by: {run.maker_name}</p>
                      <p>Approved by: {run.checker_name ?? "Waiting for approval"}</p>
                    </>
                  )}
                  <p className="text-muted text-sm">
                    {formatDateTime(run.created_at)} · {run.line_count} payments
                  </p>
                  {Object.entries(run.outcomes).map(([outcome, count]) => (
                    <p key={outcome}>
                      {outcomeLabel(outcome)}: {count}
                    </p>
                  ))}
                  <Link
                    className="underline"
                    href={moneyHref(query, {
                      batch: run.id,
                      line: undefined,
                      line_page: undefined,
                      history_page: undefined,
                    })}
                  >
                    Review run
                  </Link>
                </article>
              ))}
            </div>
            {!summary.items.length ? <p>No payment runs match this page.</p> : null}
            <nav aria-label="Payment run pages" className="flex flex-wrap gap-4 text-sm">
              {runs > 0 ? (
                <Link href={moneyHref(query, { runs: String(runs - 1) })}>Previous runs</Link>
              ) : null}
              <span>
                {summary.total} payment runs · page {runs + 1}
              </span>
              {(runs + 1) * 25 < summary.total ? (
                <Link href={moneyHref(query, { runs: String(runs + 1) })}>Next runs</Link>
              ) : null}
            </nav>
          </>
        )}
      </Panel>
    </div>
  );
}
