"use client";

import { useActionState } from "react";
import { Button } from "@/components/ui/button";
import { reviewCampaignChangeAction, type CampaignReviewActionState } from "./actions";

const initialState: CampaignReviewActionState = {};

export function CampaignChangeReviewActions({
  requestId,
  initialReason,
}: {
  requestId: string;
  initialReason?: string;
}) {
  const [state, formAction, pending] = useActionState(reviewCampaignChangeAction, initialState);
  return (
    <form action={formAction} className="flex w-full max-w-sm flex-col items-end gap-2">
      <input type="hidden" name="request_id" value={requestId} />
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
      <div className="flex gap-2">
        <Button
          type="submit"
          name="intent"
          value="approve"
          disabled={pending}
          className="h-9 px-3 text-xs"
        >
          {pending ? "Reviewing…" : "Approve change"}
        </Button>
        <Button
          type="submit"
          name="intent"
          value="reject"
          variant="danger"
          disabled={pending}
          className="h-9 px-3 text-xs"
        >
          Reject change
        </Button>
      </div>
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
