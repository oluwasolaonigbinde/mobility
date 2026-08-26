"use client";

import { useActionState } from "react";
import type { components } from "@/lib/api/schema";
import { formatDate, formatMoney } from "@/lib/format";
import { Button } from "@/components/ui/button";
import { Panel } from "@/components/ui/panel";
import { StatusChip } from "@/components/ui/status-chip";
import { requestCampaignChangeAction, type CampaignReviewActionState } from "./actions";

type ChangeRequest = components["schemas"]["CampaignChangeRead"];

const initialState: CampaignReviewActionState = {};

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
  const [state, formAction, pending] = useActionState(requestCampaignChangeAction, initialState);
  return (
    <Panel className="mt-6 p-6" aria-label="Governed campaign changes">
      <div className="mb-5">
        <h2 className="font-display text-xl font-semibold">Campaign changes</h2>
        <p className="micro text-muted mt-1">
          Preview budget or date changes without repricing accepted driver terms.
        </p>
      </div>
      <form action={formAction} className="grid gap-3 md:grid-cols-2">
        <input type="hidden" name="campaign_id" value={campaignId} />
        <input type="hidden" name="client_request_id" value={clientRequestId} />
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
            {state.error ? (
              <p role="alert" className="text-coral">
                {state.error}
              </p>
            ) : null}
            {state.done && !state.error ? <p className="text-green">✓ {state.done}</p> : null}
          </div>
          <Button type="submit" disabled={pending}>
            {pending ? "Recording…" : "Preview and request change"}
          </Button>
        </div>
      </form>
      {requests.length ? (
        <ol className="divide-edge/60 border-edge mt-6 divide-y border-t">
          {requests.map((request) => (
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
