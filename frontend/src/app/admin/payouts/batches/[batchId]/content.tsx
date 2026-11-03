import { adminValueFailure } from "@/lib/api/admin-read";
import Link from "next/link";

import { requireRole } from "@/lib/auth/current-user";

import { Panel } from "@/components/ui/panel";
import { QueueUnavailable } from "../../../queue-search";
import { moneyHref, moneyPage, type MoneyQuery } from "../../../money/navigation";
import { paymentRunStatus } from "@/lib/status/admin";
import { formatDateTime, formatMoneyExact } from "@/lib/format";
import { batchApi } from "../batch-api";
import { createApiClient } from "@/lib/api/client";
import { getSessionToken } from "@/lib/auth/session";
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
  searchParams: Promise<MoneyQuery>;
}) {
  const me = await requireRole("admin");
  const { batchId } = await params;
  const query = await searchParams;
  const page = moneyPage(query.line_page);
  const creditPage = moneyPage(query.draft_credits);
  let detail: BatchDetail;
  try {
    detail = await batchApi<BatchDetail>(`/${batchId}/detail?limit=25&offset=${page * 25}`);
  } catch (error) {
    adminValueFailure(error);
    return <QueueUnavailable />;
  }
  const batch = detail.summary;
  if (batch.id !== batchId) return <QueueUnavailable />;
  const automatic = batch.approval_mode === "automatic";
  const payoutStatus = await createApiClient(await getSessionToken())
    .GET("/api/v1/admin/payouts/automatic/status")
    .then((result) => result.data)
    .catch(adminValueFailure);
  const credits =
    batch.status === "draft" && batch.created_by_user_id === me.user.id
      ? await batchApi<Page<EligiblePayment>>(
          `/eligible?limit=25&offset=${creditPage * 25}&currency=${batch.currency}`,
        ).catch(adminValueFailure)
      : null;
  return (
    <div className="mx-auto max-w-5xl space-y-5 pb-16">
      <Link
        className="underline"
        href={moneyHref(query, {
          batch: undefined,
          line: undefined,
          line_page: undefined,
          history_page: undefined,
        })}
      >
        Back to payment runs
      </Link>
      <h3 className="font-semibold">
        {paymentRunStatus(batch)} · {formatMoneyExact(batch.total_amount, batch.currency)}
      </h3>
      <p>
        Earnings: {formatMoneyExact(batch.earnings_amount ?? batch.total_amount, batch.currency)}
        {" · "}Deduction: {formatMoneyExact(batch.deduction_amount ?? "0.00", batch.currency)}
        {" · "}To bank: {formatMoneyExact(batch.total_amount, batch.currency)}
      </p>
      <Panel className="space-y-3 p-4 sm:p-6">
        {automatic ? (
          <>
            <p>
              Approved automatically by <strong>Cardvert</strong>
              {batch.approved_at ? ` · ${formatDateTime(batch.approved_at)}` : ""}
            </p>
            <p className="text-muted text-sm">
              Follow up problems on{" "}
              <Link className="underline" href="/admin/money?tab=automatic">
                Automatic payouts
              </Link>
              .
            </p>
          </>
        ) : (
          <>
            <p>
              Prepared by: <strong>{batch.maker_name}</strong> · {formatDateTime(batch.created_at)}
            </p>
            <p>
              Approved by: <strong>{batch.checker_name ?? "Awaiting approval"}</strong>
              {batch.approved_at ? ` · ${formatDateTime(batch.approved_at)}` : ""}
            </p>
          </>
        )}
        {Object.entries(batch.outcomes).map(([outcome, count]) => (
          <p key={outcome}>
            {outcomeLabel(outcome)}: {count}
          </p>
        ))}
        {(batch.status === "reserved" && !automatic) ||
        batch.status === "reconciled" ||
        batch.status === "failed" ? (
          <BatchActions
            batchId={batchId}
            status={batch.status}
            approved={Boolean(batch.approved_at)}
            providerReady={payoutStatus?.provider_ready}
            query={query}
          />
        ) : null}
        {batch.status === "draft" && batch.created_by_user_id === me.user.id && !credits ? (
          <QueueUnavailable />
        ) : null}
        {credits ? (
          <CreateBatchForm
            entries={credits.items}
            actorId={me.user.id}
            draftId={batchId}
            draftCurrency={batch.currency}
            query={query}
          />
        ) : null}
        {batch.status === "draft" && batch.created_by_user_id !== me.user.id ? (
          <p>Only the person who prepared this can continue it.</p>
        ) : null}
      </Panel>
      {credits ? (
        <nav aria-label="Draft earnings pages" className="flex gap-3">
          {creditPage > 0 ? (
            <Link
              href={moneyHref(query, { batch: batchId, draft_credits: String(creditPage - 1) })}
            >
              Previous earnings
            </Link>
          ) : null}
          {(creditPage + 1) * 25 < credits.total ? (
            <Link
              href={moneyHref(query, { batch: batchId, draft_credits: String(creditPage + 1) })}
            >
              Next earnings
            </Link>
          ) : null}
        </nav>
      ) : null}
      <h3 className="font-display text-xl">Individual payment outcomes</h3>
      <div className="grid gap-4 md:grid-cols-2">
        {detail.lines.map((line) => (
          <Panel key={line.id} className="min-w-0 space-y-2 p-4">
            <h3 className="font-semibold break-words">{line.driver_name}</h3>
            <p>Paid to: {line.payee_name}</p>
            <p className="font-mono">{formatMoneyExact(line.amount, line.currency)}</p>
            <p>{outcomeLabel(line.outcome)}</p>
            {line.reconciled_at ? (
              <p className="text-muted text-sm">
                Payment result: {formatDateTime(line.reconciled_at)}
              </p>
            ) : null}
            <MaskedDestination versionId={line.bank_account_version_id} />
            <Link
              className="block underline"
              href={moneyHref(query, { batch: batchId, line: line.id, history_page: undefined })}
            >
              View payment history
            </Link>
            {line.status === "submitted" || line.status === "failed" ? (
              <PollLineAction lineId={line.id} />
            ) : null}
          </Panel>
        ))}
      </div>
      {!detail.lines.length ? <p className="text-muted">No payments on this page.</p> : null}
      <nav className="flex gap-4" aria-label="Payment pages">
        {page > 0 ? (
          <Link
            href={moneyHref(query, {
              batch: batchId,
              line: undefined,
              line_page: String(page - 1),
            })}
          >
            Previous
          </Link>
        ) : null}
        <span>Page {page + 1}</span>
        {(page + 1) * 25 < detail.total ? (
          <Link
            href={moneyHref(query, {
              batch: batchId,
              line: undefined,
              line_page: String(page + 1),
            })}
          >
            Next
          </Link>
        ) : null}
      </nav>
    </div>
  );
}
