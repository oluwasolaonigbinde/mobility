"use client";

import { useActionState } from "react";
import { Button } from "@/components/ui/button";
import { reviewCreativeAction, type CampaignReviewActionState } from "./actions";

const initialState: CampaignReviewActionState = {};

export function CreativeReviewActions({ creativeId }: { creativeId: string }) {
  const [state, formAction, pending] = useActionState(reviewCreativeAction, initialState);

  return (
    <form action={formAction} className="flex w-full max-w-sm flex-col items-end gap-2">
      <input type="hidden" name="creative_id" value={creativeId} />
      <label className="flex w-full flex-col gap-1">
        <span className="micro text-muted">Rejection reason</span>
        <textarea
          name="reason"
          maxLength={2000}
          aria-label="Creative rejection reason"
          placeholder="Explain what must change before resubmission"
          className="border-edge bg-raised text-ink focus:border-amber min-h-20 w-full rounded-lg border px-3 py-2 text-sm focus:outline-none"
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
          {pending ? "Reviewing…" : "Approve"}
        </Button>
        <Button
          type="submit"
          name="intent"
          value="reject"
          variant="danger"
          disabled={pending}
          className="h-9 px-3 text-xs"
        >
          Reject
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
