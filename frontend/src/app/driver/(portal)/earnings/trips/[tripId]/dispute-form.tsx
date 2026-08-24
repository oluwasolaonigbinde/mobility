"use client";

import { useActionState } from "react";
import { Button } from "@/components/ui/button";
import { submitFraudDisputeAction, type FraudDisputeActionState } from "./actions";

const initialState: FraudDisputeActionState = {};

export function DisputeForm({ flagId, tripId }: { flagId: string; tripId: string }) {
  const [state, formAction, pending] = useActionState(submitFraudDisputeAction, initialState);

  return (
    <form action={formAction} className="mt-4 flex flex-col gap-2">
      <input type="hidden" name="flag_id" value={flagId} />
      <input type="hidden" name="trip_id" value={tripId} />
      <label className="flex flex-col gap-1">
        <span className="micro text-muted">What should staff review?</span>
        <textarea
          name="message"
          required
          maxLength={2000}
          aria-label="Dispute message"
          placeholder="Explain what happened on this trip"
          className="border-edge bg-raised text-ink focus:border-amber min-h-24 w-full rounded-lg border px-3 py-2 text-sm focus:outline-none"
        />
      </label>
      <div className="flex items-start justify-between gap-3">
        <p className="micro text-faint max-w-sm">
          You can submit one dispute for this assessment. Staff will reply here.
        </p>
        <Button type="submit" disabled={pending} className="h-9 shrink-0 px-3 text-xs">
          {pending ? "Submitting…" : "Submit dispute"}
        </Button>
      </div>
      <div aria-live="polite">
        {state.error ? (
          <p role="alert" className="text-coral text-sm">
            {state.error}
          </p>
        ) : null}
        {state.done && !state.error ? <p className="text-green text-sm">✓ {state.done}</p> : null}
      </div>
    </form>
  );
}
