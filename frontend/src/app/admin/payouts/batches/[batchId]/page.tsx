import Link from "next/link";
import { notFound } from "next/navigation";
import { requireRole } from "@/lib/auth/current-user";
import { ApiError } from "@/lib/api/errors";
import { Panel } from "@/components/ui/panel";
import { PageHeader } from "@/components/ui/page-header";
import { formatDateTime, formatMoneyExact } from "@/lib/format";
import { batchApi } from "../batch-api";
import { BatchActions, CreateBatchForm, MaskedDestination, PollLineAction } from "../batch-forms";
import {
  outcomeLabel,
  type BatchDetail,
  type EligiblePayment,
  type Page,
} from "../operation-types";

export default async function BatchDetailPage({
  params,
  searchParams,
}: {
  params: Promise<{ batchId: string }>;
  searchParams: Promise<{ page?: string }>;
}) {
  const me = await requireRole("admin");
  const { batchId } = await params;
  const query = await searchParams;
  const page = /^\d+$/.test(query.page ?? "") ? Math.min(Number(query.page), 100000) : 0;
  let detail: BatchDetail;
  try {
    detail = await batchApi<BatchDetail>(`/${batchId}/detail?limit=25&offset=${page * 25}`);
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) notFound();
    throw error;
  }
  const batch = detail.summary;
  const credits =
    batch.status === "draft" && batch.created_by_user_id === me.user.id
      ? await batchApi<Page<EligiblePayment>>(
          `/eligible?limit=25&offset=${page * 25}&currency=${batch.currency}`,
        )
      : null;
  return (
    <div className="mx-auto max-w-5xl space-y-5 pb-16">
      <Link className="underline" href="/admin/payouts/batches">
        Back to payout batches
      </Link>
      <PageHeader
        title="Payout batch review"
        eyebrow={`${batch.status} · ${formatMoneyExact(batch.total_amount, batch.currency)}`}
      />
      <Panel className="space-y-3 p-4 sm:p-6">
        <p>
          Maker: <strong>{batch.maker_name}</strong> · {formatDateTime(batch.created_at)}
        </p>
        <p>
          Checker: <strong>{batch.checker_name ?? "Awaiting independent approval"}</strong>
          {batch.approved_at ? ` · ${formatDateTime(batch.approved_at)}` : ""}
        </p>
        <p className="text-muted text-sm">
          A different administrator must approve frozen instructions. Submission is queued first;
          provider evidence determines each line&apos;s outcome. Manual verification requires a
          third administrator.
        </p>
        {Object.entries(batch.outcomes).map(([outcome, count]) => (
          <p key={outcome}>
            {outcomeLabel(outcome)}: {count}
          </p>
        ))}
        {batch.status === "reserved" ||
        batch.status === "reconciled" ||
        batch.status === "failed" ? (
          <BatchActions batchId={batchId} status={batch.status} />
        ) : null}
        {credits ? (
          <CreateBatchForm
            entries={credits.items}
            actorId={me.user.id}
            draftId={batchId}
            draftCurrency={batch.currency}
          />
        ) : null}
        {batch.status === "draft" && !credits ? (
          <p>Only the maker can reserve this draft.</p>
        ) : null}
      </Panel>
      <h2 className="font-display text-xl">Individual payment outcomes</h2>
      <div className="grid gap-4 md:grid-cols-2">
        {detail.lines.map((line) => (
          <Panel key={line.id} className="min-w-0 space-y-2 p-4">
            <h3 className="font-semibold break-words">{line.driver_name}</h3>
            <p>Payee: {line.payee_name}</p>
            <p className="font-mono">{formatMoneyExact(line.amount, line.currency)}</p>
            <p>{outcomeLabel(line.outcome)}</p>
            {line.reconciled_at ? (
              <p className="text-muted text-sm">
                Provider evidence: {formatDateTime(line.reconciled_at)} ·{" "}
                {line.reconciler_name ?? "Verified provider event"}
              </p>
            ) : null}
            <MaskedDestination versionId={line.bank_account_version_id} />
            <Link
              className="block underline"
              href={`/admin/payouts/batches/${batchId}/lines/${line.id}`}
            >
              View line history
            </Link>
            {line.status === "submitted" || line.status === "failed" ? (
              <PollLineAction lineId={line.id} />
            ) : null}
          </Panel>
        ))}
      </div>
      {!detail.lines.length ? <p className="text-muted">No payment lines on this page.</p> : null}
      <nav className="flex gap-4" aria-label="Payment line pages">
        {page > 0 ? <Link href={`?page=${page - 1}`}>Previous</Link> : null}
        <span>Page {page + 1}</span>
        {(page + 1) * 25 < (credits?.total ?? detail.total) ? (
          <Link href={`?page=${page + 1}`}>Next</Link>
        ) : null}
      </nav>
    </div>
  );
}
