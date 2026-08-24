"use client";

import { useActionState } from "react";
import { Button } from "@/components/ui/button";
import { replyFraudDisputeAction, type FraudDisputeReplyActionState } from "./actions";

const initialState: FraudDisputeReplyActionState = {};

export function DisputeReplyActions({ disputeId }: { disputeId: string }) {
  const [state, formAction, pending] = useActionState(replyFraudDisputeAction, initialState);

  return (
    <form action={formAction} className="mt-3 flex max-w-xl flex-col gap-2">
      <input type="hidden" name="dispute_id" value={disputeId} />
      <label className="flex flex-col gap-1">
        <span className="micro text-muted">Reply to driver</span>
        <textarea
          name="reply"
          required
          maxLength={2000}
          aria-label="Reply to driver"
          placeholder="Give the driver a clear outcome or next step"
          className="border-edge bg-raised text-ink focus:border-amber min-h-20 w-full rounded-lg border px-3 py-2 text-sm focus:outline-none"
        />
      </label>
      <Button type="submit" disabled={pending} className="h-9 self-start px-3 text-xs">
        {pending ? "Sending…" : "Send reply"}
      </Button>
      <div aria-live="polite">
        {state.error ? (
          <p role="alert" className="text-coral text-xs">
            {state.error}
          </p>
        ) : null}
        {state.done && !state.error ? <p className="text-green text-xs">✓ {state.done}</p> : null}
      </div>
    </form>
  );
}
