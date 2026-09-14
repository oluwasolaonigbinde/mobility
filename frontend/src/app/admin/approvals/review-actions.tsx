"use client";

import { useActionState } from "react";
import { reviewCampaignAction, type CampaignReviewActionState } from "./actions";
import { DecisionButtons } from "./decision-buttons";

const initialState: CampaignReviewActionState = {};

export function ReviewActions({ campaignId }: { campaignId: string }) {
  const [state, formAction] = useActionState(reviewCampaignAction, initialState);

  return (
    <form action={formAction} className="flex w-full max-w-sm flex-col items-end gap-2">
      <input type="hidden" name="campaign_id" value={campaignId} />
      <label className="flex w-full flex-col gap-1">
        <span className="micro text-muted">Rejection reason</span>
        <textarea
          name="reason"
          maxLength={2000}
          aria-label="Rejection reason"
          placeholder="Explain what must change before resubmission"
          className="border-edge bg-raised text-ink focus:border-amber min-h-20 w-full rounded-lg border px-3 py-2 text-sm focus:outline-none"
        />
      </label>
      <DecisionButtons />
      <div aria-live="polite">
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
