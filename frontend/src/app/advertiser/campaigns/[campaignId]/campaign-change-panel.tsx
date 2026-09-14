"use client";

import { useActionState, useEffect, useRef, useState } from "react";
import type { components } from "@/lib/api/schema";
import { formatDate, formatMoney } from "@/lib/format";
import { Button } from "@/components/ui/button";
import { Panel } from "@/components/ui/panel";
import { StatusChip } from "@/components/ui/status-chip";
import {
  confirmCampaignChangeAction,
  previewCampaignChangeAction,
  type CampaignReviewActionState,
} from "./actions";

type ChangeRequest = components["schemas"]["CampaignChangeRead"];

const initialState: CampaignReviewActionState = {};

const outcomeCopy = {
  apply_now: "This change can apply as soon as you confirm it.",
  await_review: "After confirmation, Cardvert must review this change before it can apply.",
  await_funding: "After confirmation, this change will wait for enough recorded funding.",
} as const;

function exactValue(value: unknown): string {
  if (value === null || value === undefined) return "Not set";
  return String(value);
}

export function CampaignChangePanel({
  campaignId,
  clientRequestId,
  currency,
  requests,
}: {
  campaignId: string;
  clientRequestId: string;
  currency: string;
  requests: ChangeRequest[];
}) {
  const [commandId, setCommandId] = useState(clientRequestId);
  const [clearedPreviewCommandId, setClearedPreviewCommandId] = useState<string>();
  const [confirmedRequests, setConfirmedRequests] = useState<ChangeRequest[]>([]);
  const recordedConfirmation = useRef<string | undefined>(undefined);
  const [previewState, previewAction, previewPending] = useActionState(
    previewCampaignChangeAction,
    initialState,
  );
  const [confirmState, confirmAction, confirmPending] = useActionState(
    confirmCampaignChangeAction,
    initialState,
  );
  useEffect(() => {
    const confirmed = confirmState.confirmedRequest;
    if (!confirmed || !confirmState.commandId || recordedConfirmation.current === confirmed.id)
      return;
    recordedConfirmation.current = confirmed.id;
    setClearedPreviewCommandId(confirmState.commandId);
    setConfirmedRequests((current) => [
      confirmed,
      ...current.filter((item) => item.id !== confirmed.id),
    ]);
    setCommandId(crypto.randomUUID());
  }, [confirmState.commandId, confirmState.confirmedRequest]);

  const previewIsCurrent =
    Boolean(previewState.commandId) && previewState.commandId !== clearedPreviewCommandId;
  const proposal = previewIsCurrent ? previewState.proposal : undefined;
  const preview = previewIsCurrent ? previewState.preview : undefined;
  const currentConfirmation = confirmState.confirmedRequest;
  const localRequests = currentConfirmation
    ? [
        currentConfirmation,
        ...confirmedRequests.filter((item) => item.id !== currentConfirmation.id),
      ]
    : confirmedRequests;
  const visibleRequests = [
    ...localRequests,
    ...requests.filter((item) => !localRequests.some((confirmed) => confirmed.id === item.id)),
  ];
  return (
    <Panel className="mt-6 p-6" aria-label="Governed campaign changes">
      <div className="mb-5">
        <h2 className="font-display text-xl font-semibold">Campaign changes</h2>
        <p className="micro text-muted mt-1">
          Preview budget or date changes without repricing accepted driver terms.
        </p>
      </div>
      <form key={commandId} action={previewAction} className="grid gap-3 md:grid-cols-2">
        <input type="hidden" name="campaign_id" value={campaignId} />
        <input type="hidden" name="client_request_id" value={commandId} />
        <label className="text-sm">
          <span className="micro text-muted">Total budget</span>
          <input
            name="budget_amount"
            inputMode="decimal"
            placeholder={`Amount in ${currency}`}
            className="border-edge bg-raised mt-1 h-11 w-full rounded-lg border px-3.5"
          />
        </label>
        <label className="text-sm">
          <span className="micro text-muted">Daily budget</span>
          <input
            name="daily_budget_amount"
            inputMode="decimal"
            placeholder={`Amount in ${currency}`}
            className="border-edge bg-raised mt-1 h-11 w-full rounded-lg border px-3.5"
          />
        </label>
        <label className="text-sm">
          <span className="micro text-muted">New start (Lagos time)</span>
          <input
            name="start_at"
            type="datetime-local"
            className="border-edge bg-raised mt-1 h-11 w-full rounded-lg border px-3.5"
          />
        </label>
        <label className="text-sm">
          <span className="micro text-muted">New end (Lagos time)</span>
          <input
            name="end_at"
            type="datetime-local"
            className="border-edge bg-raised mt-1 h-11 w-full rounded-lg border px-3.5"
          />
        </label>
        <label className="text-sm md:col-span-2">
          <span className="micro text-muted">Reason</span>
          <textarea
            name="reason"
            required
            maxLength={1000}
            className="border-edge bg-raised mt-1 min-h-20 w-full rounded-lg border px-3.5 py-2"
            placeholder="Explain why this change is needed"
          />
        </label>
        <div className="flex items-center justify-between gap-3 md:col-span-2">
          <div aria-live="polite" className="text-sm">
            {previewState.error ? (
              <p role="alert" className="text-coral">
                {previewState.error}
              </p>
            ) : null}
          </div>
          <Button type="submit" disabled={previewPending}>
            {previewPending ? "Checking…" : "Preview change"}
          </Button>
        </div>
      </form>
      {confirmState.done && !confirmState.error ? (
        <p role="status" className="text-green mt-4 text-sm">
          ✓ {confirmState.done}
        </p>
      ) : null}
      {preview && proposal ? (
        <div
          className="border-amber/40 bg-amber/5 mt-5 rounded-lg border p-4"
          aria-label="Change preview"
        >
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <h3 className="font-medium">Review before confirming</h3>
              <p className="text-muted mt-1 text-sm">
                {outcomeCopy[preview.outcome as keyof typeof outcomeCopy] ??
                  "Cardvert will recheck this change when you confirm."}
              </p>
            </div>
            <StatusChip tone={preview.outcome === "apply_now" ? "green" : "amber"}>
              {preview.outcome === "apply_now"
                ? "Can apply now"
                : preview.outcome === "await_review"
                  ? "Needs review"
                  : "Needs funding"}
            </StatusChip>
          </div>
          <dl className="mt-4 grid gap-3 text-sm md:grid-cols-2">
            {Object.entries(preview.after)
              .filter(([field, value]) => value !== preview.before[field])
              .map(([field, value]) => (
                <div key={field}>
                  <dt className="micro text-muted">{field.replaceAll("_", " ")}</dt>
                  <dd className="mt-1 font-mono text-xs break-all">
                    {exactValue(preview.before[field])} → {exactValue(value)}
                  </dd>
                </div>
              ))}
            <div>
              <dt className="micro text-muted">Additional driver liability</dt>
              <dd className="mt-1 font-mono text-xs">
                {preview.currency} {preview.requested_liability_amount}
              </dd>
            </div>
            <div>
              <dt className="micro text-muted">Recorded liability headroom</dt>
              <dd className="mt-1 font-mono text-xs">
                {preview.currency} {preview.available_liability_amount}
              </dd>
            </div>
          </dl>
          <form
            action={confirmAction}
            className="mt-4 flex flex-wrap items-center justify-between gap-3"
          >
            <input type="hidden" name="campaign_id" value={campaignId} />
            <input
              type="hidden"
              name="client_request_id"
              value={previewState.commandId ?? commandId}
            />
            <input type="hidden" name="source_sha256" value={preview.source_sha256} />
            <input type="hidden" name="preview_sha256" value={preview.preview_sha256} />
            <input type="hidden" name="budget_amount" value={proposal.budgetAmount ?? ""} />
            <input
              type="hidden"
              name="daily_budget_amount"
              value={proposal.dailyBudgetAmount ?? ""}
            />
            <input type="hidden" name="start_at" value={proposal.startAt ?? ""} />
            <input type="hidden" name="end_at" value={proposal.endAt ?? ""} />
            <input type="hidden" name="reason" value={proposal.reason} />
            <div aria-live="polite" className="text-sm">
              {confirmState.error ? (
                <p role="alert" className="text-coral">
                  {confirmState.error}
                </p>
              ) : null}
            </div>
            <Button type="submit" disabled={confirmPending}>
              {confirmPending ? "Confirming…" : "Confirm this change"}
            </Button>
          </form>
        </div>
      ) : null}
      {visibleRequests.length ? (
        <ol className="divide-edge/60 border-edge mt-6 divide-y border-t">
          {visibleRequests.map((request) => (
            <li key={request.id} className="py-4">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <StatusChip
                  tone={
                    request.status === "applied"
                      ? "green"
                      : request.status === "rejected"
                        ? "coral"
                        : "amber"
                  }
                >
                  {request.status.replaceAll("_", " ")}
                </StatusChip>
                <span className="micro text-faint">{formatDate(request.created_at)}</span>
              </div>
              <p className="text-muted mt-2 text-sm">
                {request.classifications.join(" · ")} · additional driver liability{" "}
                {formatMoney(request.requested_liability_amount, currency)}
              </p>
              {request.review_reason ? (
                <p className="mt-1 text-sm">Decision: {request.review_reason}</p>
              ) : null}
            </li>
          ))}
        </ol>
      ) : null}
    </Panel>
  );
}
