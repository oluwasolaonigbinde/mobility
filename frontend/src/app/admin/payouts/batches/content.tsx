import { adminValueFailure } from "@/lib/api/admin-read";
import Link from "next/link";
import { Panel } from "@/components/ui/panel";
import { requireRole } from "@/lib/auth/current-user";
import { formatDateTime, formatMoneyExact } from "@/lib/format";
import { adminStatus, paymentRunStatus } from "@/lib/status/admin";
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

/** Ready to pay: available earnings and the form that prepares a payment run from them. */
export async function ReadyToPay({ searchParams }: { searchParams: Promise<MoneyQuery> }) {
  const me = await requireRole("admin"),
    query = await searchParams;
  const credits = moneyPage(query.credits);
  const filters = new URLSearchParams({ limit: "25", offset: String(credits * 25) });
  if (query.q) filters.set("search", query.q.slice(0, 100));
  if (query.currency && /^[a-z]{3}$/i.test(query.currency))
    filters.set("currency", query.currency.toUpperCase());
  const entries = await batchApi<Page<EligiblePayment>>(`/eligible?${filters}`).catch(
    adminValueFailure,
  );
  return (
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
              {entries.items.filter((entry) => entry.eligible).length} payable earnings{" "}
              {entries.items.filter((entry) => entry.eligible).length === 1 ? "record" : "records"}{" "}
              on this page · page {credits + 1}
            </span>
            {(credits + 1) * 25 < entries.total ? (
              <Link href={moneyHref(query, { credits: String(credits + 1) })}>Next earnings</Link>
            ) : null}
          </nav>
        </>
      )}
    </Panel>
  );
}

const STATUSES = ["draft", "reserved", "submitted", "reconciled", "completed", "failed", "void"];

/** Payment runs: one compact row per run; details, approval and history open in the drawer. */
export default async function PaymentRuns({ searchParams }: { searchParams: Promise<MoneyQuery> }) {
  await requireRole("admin");
  const query = await searchParams;
  const runs = moneyPage(query.runs);
  const runFilters = new URLSearchParams({ limit: "25", offset: String(runs * 25) });
  const runStatus = query.status && STATUSES.includes(query.status) ? query.status : undefined;
  if (runStatus) runFilters.set("batch_status", runStatus);
  const summary = await batchApi<Page<BatchSummary>>(`/summaries?${runFilters}`).catch(
    adminValueFailure,
  );
  return (
    <Panel className="space-y-4 p-4 sm:p-6">
      <h2 className="font-display text-xl">Payment runs</h2>
      <FilterChips
        label="Payment run status"
        items={[
          {
            href: moneyHref(query, { status: undefined, runs: undefined }),
            label: "All statuses",
            active: !runStatus,
          },
          ...STATUSES.map((status) => ({
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
          {summary.items.length ? (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[640px] text-sm">
                <thead>
                  <tr className="text-muted border-edge border-b text-left">
                    <th className="py-2 font-normal">Status</th>
                    <th className="py-2 text-right font-normal">Total</th>
                    <th className="py-2 pl-4 font-normal">Created</th>
                    <th className="py-2 font-normal">Payments</th>
                    <th className="py-2">
                      <span className="sr-only">Open</span>
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {summary.items.map((run) => (
                    <tr key={run.id} className="border-edge/60 border-b align-top last:border-0">
                      <td className="py-2">
                        {paymentRunStatus(run)}
                        {run.approval_mode === "automatic" ? (
                          <span className="text-muted block text-xs">Automatic</span>
                        ) : null}
                      </td>
                      <td className="py-2 text-right font-medium">
                        {formatMoneyExact(run.total_amount, run.currency)}
                      </td>
                      <td className="py-2 pl-4">{formatDateTime(run.created_at)}</td>
                      <td className="py-2">
                        {run.line_count}
                        {Object.keys(run.outcomes).length ? (
                          <span className="text-muted block text-xs">
                            {Object.entries(run.outcomes)
                              .map(([outcome, count]) => `${outcomeLabel(outcome)}: ${count}`)
                              .join(" · ")}
                          </span>
                        ) : null}
                      </td>
                      <td className="py-2 text-right">
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
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p>No payment runs match this page.</p>
          )}
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
  );
}
