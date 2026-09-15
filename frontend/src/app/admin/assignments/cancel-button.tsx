"use client";

import { useState, useTransition } from "react";
import { cancelAssignmentAction } from "./actions";
import { Field } from "@/components/ui/field";

export function CancelAssignmentButton({
  assignmentId,
  assignmentLabel,
}: {
  assignmentId: string;
  assignmentLabel: string;
}) {
  const [pending, startTransition] = useTransition();
  const [error, setError] = useState<string>();
  const [confirming, setConfirming] = useState(false);

  function run(reason: string) {
    setError(undefined);
    startTransition(async () => {
      const result = await cancelAssignmentAction(assignmentId, reason.trim());
      if (!result.error) setConfirming(false);
      if (result.error) setError(result.error);
    });
  }

  return (
    <div className="flex flex-col items-end gap-1">
      <button
        type="button"
        onClick={() => setConfirming(true)}
        disabled={pending}
        className="micro text-muted hover:text-coral transition-colors disabled:opacity-50"
      >
        {pending ? "…" : "Cancel"}
      </button>
      {error ? (
        <p role="alert" className="text-coral text-xs">
          {error}
        </p>
      ) : null}
      {confirming ? (
        <div
          role="alertdialog"
          aria-modal="true"
          aria-labelledby="cancel-assignment-title"
          className="bg-bg/80 fixed inset-0 z-50 grid place-items-center p-4 text-left backdrop-blur-sm"
          onKeyDown={(event) => {
            if (event.key === "Escape" && !pending) setConfirming(false);
          }}
        >
          <form
            className="border-coral/40 bg-panel w-full max-w-md rounded-xl border p-5 shadow-xl"
            onSubmit={(event) => {
              event.preventDefault();
              const reason = new FormData(event.currentTarget).get("reason");
              if (typeof reason === "string" && reason.trim()) run(reason);
            }}
          >
            <h2 id="cancel-assignment-title" className="font-display text-lg font-semibold">
              Cancel {assignmentLabel}?
            </h2>
            <p className="text-muted mt-2 text-sm">
              The driver will stop earning from this assignment. The reason is recorded permanently.
            </p>
            <div className="mt-4">
              <Field label="Cancellation reason" name="reason" required autoFocus />
            </div>
            {error ? (
              <p role="alert" className="text-coral mt-3 text-xs">
                {error}
              </p>
            ) : null}
            <div className="mt-5 flex flex-col gap-2 sm:flex-row sm:justify-end">
              <button type="button" disabled={pending} onClick={() => setConfirming(false)}>
                Keep assignment
              </button>
              <button type="submit" className="text-coral" disabled={pending}>
                {pending ? "Cancelling…" : "Confirm cancellation"}
              </button>
            </div>
          </form>
        </div>
      ) : null}
    </div>
  );
}
