"use client";

import { useActionState } from "react";
import { reviewCampaignChangeAction, type CampaignReviewActionState } from "./actions";
import { DecisionButtons } from "./decision-buttons";

const initialState: CampaignReviewActionState = {};

export function CampaignChangeReviewActions({
  requestId,
  initialReason,
  pendingFunding = false,
}: {
  requestId: string;
  initialReason?: string;
  pendingFunding?: boolean;
}) {
  const [state, formAction] = useActionState(reviewCampaignChangeAction, initialState);
  return (
    <form action={formAction} className="flex w-full max-w-sm flex-col items-end gap-2">
      <input type="hidden" name="request_id" value={requestId} />
      {pendingFunding ? (
        <p className="text-muted text-sm">
          This change is approved. The approval stays in place. When there is enough funding, press
          Retry approved change to apply it.
        </p>
      ) : null}
      <label className="flex w-full flex-col gap-1">
        <span className="micro text-muted">Decision reason</span>
        <textarea
          name="reason"
          defaultValue={initialReason}
          required
          maxLength={1000}
          aria-label="Campaign change decision reason"
          className="border-edge bg-raised text-ink focus:border-amber min-h-20 w-full rounded-lg border px-3 py-2 text-sm focus:outline-none"
          placeholder="Record why this change is approved or rejected"
        />
      </label>
      <DecisionButtons
        approveLabel={pendingFunding ? "Retry approved change" : "Approve change"}
        rejectLabel="Reject change"
        allowReject={!pendingFunding}
      />
      <div aria-live="polite">
        {state.notice && !state.error ? (
          <p className="text-muted text-right text-xs">{state.notice}</p>
        ) : null}
        {state.error ? (
          <p role="alert" className="text-coral text-right text-xs">
            {state.error}
          </p>
        ) : null}
        {state.done && !state.error ? (
          <p className="text-green text-right text-xs">✓ {state.done}</p>
        ) : null}
      </div>
    </form>
  );
}
