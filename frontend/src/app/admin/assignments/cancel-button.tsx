"use client";

import { useState, useTransition } from "react";
import { cancelAssignmentAction } from "./actions";

export function CancelAssignmentButton({ assignmentId }: { assignmentId: string }) {
  const [pending, startTransition] = useTransition();
  const [error, setError] = useState<string>();

  function run() {
    if (!window.confirm("Cancel this assignment? The driver stops earning from it.")) return;
    setError(undefined);
    startTransition(async () => {
      const result = await cancelAssignmentAction(assignmentId);
      if (result.error) setError(result.error);
    });
  }

  return (
    <div className="flex flex-col items-end gap-1">
      <button
        type="button"
        onClick={run}
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
    </div>
  );
}
