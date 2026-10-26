"use client";

import { useActionState } from "react";
import { Button } from "@/components/ui/button";
import type { components } from "@/lib/api/schema";
import { reviewFraudFlagAction, type FraudReviewActionState } from "./actions";

type FraudFlagStatus = components["schemas"]["FraudFlagStatus"];

const initialState: FraudReviewActionState = {};

const effects = {
  confirm: "Keeps this trip's held pay held. Record any money correction separately with a reason.",
  clear: "Removes this hold. Held pay is released only when a fresh check finds it is still owed.",
};

export function ReviewActions({ flagId, status }: { flagId: string; status: FraudFlagStatus }) {
  const [state, formAction, pending] = useActionState(reviewFraudFlagAction, initialState);

  if (status === "confirmed" || status === "dismissed") {
    return (
      <p className="text-muted text-sm">
        {status === "confirmed"
          ? "Problem confirmed — held pay stays held; review is final."
          : "Cleared — review is final; hold removed. Held pay is released only when a fresh check finds it is still owed."}
      </p>
    );
  }

  return (
    <form action={formAction} className="flex w-full flex-col gap-3">
      <input type="hidden" name="flag_id" value={flagId} />

      <>
        <label className="flex w-full flex-col gap-1">
          <span className="text-ink text-sm font-medium">Review note</span>
          <textarea
            name="note"
            required
            maxLength={2000}
            aria-label="Review note"
            placeholder="Explain the evidence behind this decision"
            className="border-edge bg-raised text-ink focus:border-amber min-h-20 w-full rounded-lg border px-3 py-2 text-sm focus:outline-none"
          />
        </label>
        <div className="grid gap-3 sm:grid-cols-2">
          <div className="flex flex-col items-start gap-1">
            <Button
              type="submit"
              name="intent"
              value="confirm"
              disabled={pending}
              variant="danger"
              aria-describedby={`${flagId}-confirm-effect`}
              className="h-9 px-3 text-xs"
            >
              Confirm problem
            </Button>
            <p id={`${flagId}-confirm-effect`} className="text-muted text-xs">
              {effects.confirm}
            </p>
          </div>
          <div className="flex flex-col items-start gap-1">
            <Button
              type="submit"
              name="intent"
              value="dismiss"
              disabled={pending}
              variant="ghost"
              aria-describedby={`${flagId}-clear-effect`}
              className="h-9 px-3 text-xs"
            >
              Clear
            </Button>
            <p id={`${flagId}-clear-effect`} className="text-muted text-xs">
              {effects.clear}
            </p>
          </div>
        </div>
      </>

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
