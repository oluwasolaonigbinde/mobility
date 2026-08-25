"use client";

import { useState, useTransition } from "react";
import { activateAssignmentAction } from "./actions";

export function ActivateAssignmentButton({ assignmentId }: { assignmentId: string }) {
  const [pending, startTransition] = useTransition();
  const [error, setError] = useState<string>();

  function run() {
    setError(undefined);
    startTransition(async () => {
      const result = await activateAssignmentAction(assignmentId);
      if (result.error) setError(result.error);
    });
  }

  return (
    <div className="flex flex-col items-end gap-1">
      <button
        type="button"
        onClick={run}
        disabled={pending}
        className="micro text-amber hover:text-amber-soft transition-colors disabled:opacity-50"
      >
        {pending ? "…" : "Activate"}
      </button>
      {error ? (
        <p role="alert" className="text-coral text-xs">
          {error}
        </p>
      ) : null}
    </div>
  );
}
