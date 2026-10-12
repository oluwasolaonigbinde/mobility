"use client";

import { useActionState } from "react";
import { Button } from "@/components/ui/button";
import type { components } from "@/lib/api/schema";
import { reviewFraudFlagAction, type FraudReviewActionState } from "./actions";

type FraudFlagStatus = components["schemas"]["FraudFlagStatus"];

const initialState: FraudReviewActionState = {};

/** One plain line per decision, from the trip's money effect. */
export function decisionEffects({
  reversalRecommended,
  reversalAmount,
}: {
  reversalRecommended: boolean;
  reversalAmount?: string;
}) {
  return {
    start: "Marks this trip as being reviewed. Any held pay stays held.",
    confirm: reversalRecommended
      ? `Reverses ${reversalAmount ?? "the pay"} of this trip's released earnings. This is final.`
      : "Keeps this trip's held pay held. This is final.",
    clear:
      "Removes this hold. Held pay is released only when a fresh check finds it is still owed.",
  };
}

export function ReviewActions({
  flagId,
  status,
  reversalRecommended = false,
  reversalRecorded = false,
  reversalAmount,
}: {
  flagId: string;
  status: FraudFlagStatus;
  reversalRecommended?: boolean;
  reversalRecorded?: boolean;
  /** Formatted amount already available or paid for the trip, shown when a reversal applies. */
  reversalAmount?: string;
}) {
  const [state, formAction, pending] = useActionState(reviewFraudFlagAction, initialState);
  const effects = decisionEffects({ reversalRecommended, reversalAmount });

  if (status === "confirmed" || status === "dismissed") {
    return (
      <p className="text-muted text-sm">
        {status === "confirmed"
          ? reversalRecorded
            ? "Problem confirmed — this trip's released earnings were reversed."
            : "Problem confirmed — held pay stays held; review is final."
          : "Cleared — review is final; hold removed. Held pay is released only when a fresh check finds it is still owed."}
      </p>
    );
  }

  return (
    <form action={formAction} className="flex w-full flex-col gap-3">
      <input type="hidden" name="flag_id" value={flagId} />

      {status === "open" ? (
        <div className="flex flex-col items-start gap-1">
          <Button
            type="submit"
            name="intent"
            value="acknowledge"
            disabled={pending}
            aria-describedby={`${flagId}-start-effect`}
            className="h-9 px-3 text-xs"
          >
            {pending ? "Starting review…" : "Start review"}
          </Button>
          <p id={`${flagId}-start-effect`} className="text-muted text-xs">
            {effects.start}
          </p>
        </div>
      ) : (
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
                {reversalRecommended
                  ? "Confirm problem & reverse released earnings"
                  : "Confirm problem"}
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
      )}

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
