import Link from "next/link";
import { requireRole } from "@/lib/auth/current-user";
import type { components } from "@/lib/api/schema";
import { formatDateTime, formatMoneyExact } from "@/lib/format";
import { Panel } from "@/components/ui/panel";
import { QueueUnavailable } from "../../../../../queue-search";
import { moneyHref, moneyPage, type MoneyQuery } from "../../../../../money/navigation";
import { batchApi, type PayoutBatch } from "../../../batch-api";
import { outcomeLabel } from "../../../operation-types";
import { PollLineAction } from "../../../batch-forms";
export default async function PaymentHistory({
  params,
  searchParams,
}: {
  params: Promise<{ batchId: string; lineId: string }>;
  searchParams: Promise<MoneyQuery>;
}) {
  await requireRole("admin");
  const { batchId, lineId } = await params,
    query = await searchParams;
  let parent: PayoutBatch;
  try {
    parent = await batchApi<PayoutBatch>(`/${batchId}`);
  } catch {
    return <QueueUnavailable />;
  }
  if (parent.id !== batchId || !Array.isArray(parent.lines)) return <QueueUnavailable />;
  const line = parent.lines.find((candidate) => candidate.id === lineId);
  if (!line) return <p role="alert">That payment is not part of this payment run.</p>;
  const page = moneyPage(query.history_page);
  let history: components["schemas"]["PayoutLineHistoryRead"];
  try {
    history = await batchApi<components["schemas"]["PayoutLineHistoryRead"]>(
      `/lines/${lineId}/history?limit=25&offset=${page * 25}`,
    );
  } catch {
    return <QueueUnavailable />;
  }
  return (
    <div className="space-y-4">
      <Link
        className="underline"
        href={moneyHref(query, { batch: batchId, line: undefined, history_page: undefined })}
      >
        Back to payment run
      </Link>
      <p>{formatMoneyExact(line.amount, line.currency)}</p>
      <p>
        Latest provider answer:{" "}
        {history.latest_submission_outcome
          ? outcomeLabel(history.latest_submission_outcome)
          : "No provider answer recorded"}
      </p>
      {history.items.map((event) => (
        <Panel key={event.id} className="space-y-2 p-4">
          <p>
            {outcomeLabel(event.outcome)} ·{" "}
            {event.applied ? "Applied to this payment" : "Recorded without changing this payment"}
          </p>
          <p>
            {event.source === "webhook"
              ? "Provider event"
              : event.source === "poll"
                ? "Provider check"
                : "Verified check"}{" "}
            · provider time {formatDateTime(event.provider_occurred_at)}
          </p>
          <p className="text-muted text-sm">Recorded {formatDateTime(event.created_at)}</p>
        </Panel>
      ))}
      {!history.items.length ? (
        <p>No verified final result has been recorded. This does not mean failed or paid.</p>
      ) : null}
      {line.status === "submitted" || line.status === "failed" ? (
        <PollLineAction lineId={lineId} />
      ) : null}
      <nav aria-label="History pages" className="flex gap-4">
        {page > 0 ? (
          <Link
            href={moneyHref(query, {
              batch: batchId,
              line: lineId,
              history_page: String(page - 1),
            })}
          >
            Previous
          </Link>
        ) : null}
        <span>Page {page + 1}</span>
        {(page + 1) * 25 < history.total ? (
          <Link
            href={moneyHref(query, {
              batch: batchId,
              line: lineId,
              history_page: String(page + 1),
            })}
          >
            Next
          </Link>
        ) : null}
      </nav>
    </div>
  );
}
