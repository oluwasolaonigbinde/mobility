"use client";

import { useActionState } from "react";
import { Button } from "@/components/ui/button";
import type { components } from "@/lib/api/schema";
import { reviewFraudFlagAction, type FraudReviewActionState } from "./actions";

type FraudFlagStatus = components["schemas"]["FraudFlagStatus"];

const initialState: FraudReviewActionState = {};

export function ReviewActions({ flagId, status }: { flagId: string; status: FraudFlagStatus }) {
  const [state, formAction, pending] = useActionState(reviewFraudFlagAction, initialState);

  if (status === "confirmed" || status === "dismissed") {
    return (
      <p className="micro text-faint text-right">
        {status === "confirmed"
          ? "Confirmed fraud — review is final."
          : "Dismissed — review is final."}
      </p>
    );
  }

  return (
    <form action={formAction} className="flex w-full max-w-sm flex-col items-end gap-2">
      <input type="hidden" name="flag_id" value={flagId} />

      {status === "open" ? (
        <Button
          type="submit"
          name="intent"
          value="acknowledge"
          disabled={pending}
          className="h-9 px-3 text-xs"
        >
          {pending ? "Acknowledging…" : "Acknowledge"}
        </Button>
      ) : (
        <>
          <label className="flex w-full flex-col gap-1">
            <span className="micro text-muted">Review note</span>
            <textarea
              name="note"
              required
              maxLength={2000}
              aria-label="Review note"
              placeholder="Explain the evidence behind this decision"
              className="border-edge bg-raised text-ink focus:border-amber min-h-20 w-full rounded-lg border px-3 py-2 text-sm focus:outline-none"
            />
          </label>
          <div className="flex gap-2">
            <Button
              type="submit"
              name="intent"
              value="confirm"
              disabled={pending}
              variant="danger"
              className="h-9 px-3 text-xs"
            >
              Confirm fraud
            </Button>
            <Button
              type="submit"
              name="intent"
              value="dismiss"
              disabled={pending}
              variant="ghost"
              className="h-9 px-3 text-xs"
            >
              Dismiss flag
            </Button>
          </div>
        </>
      )}

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
