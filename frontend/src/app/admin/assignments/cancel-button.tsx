"use client";

import { useRef, useState, useTransition } from "react";
import { cancelAssignmentAction } from "./actions";
import { Field } from "@/components/ui/field";
import { ConfirmationDialog } from "@/components/ui/confirmation-dialog";

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
  const [reason, setReason] = useState("");
  const triggerRef = useRef<HTMLButtonElement>(null);

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
        ref={triggerRef}
        type="button"
        onClick={() => {
          setError(undefined);
          setReason("");
          setConfirming(true);
        }}
        disabled={pending}
        className="micro text-muted hover:text-coral transition-colors disabled:opacity-50"
      >
        {pending ? "…" : "Cancel"}
      </button>
      <ConfirmationDialog
        open={confirming}
        onOpenChange={setConfirming}
        title={`Cancel ${assignmentLabel}?`}
        description="The driver will stop earning from this assignment. The reason is recorded permanently."
        cancelLabel="Keep assignment"
        confirmLabel="Confirm cancellation"
        onConfirm={() => {
          if (reason.trim()) run(reason);
        }}
        returnFocusRef={triggerRef}
        pending={pending}
        error={error}
      >
        <Field
          label="Cancellation reason"
          name="reason"
          required
          value={reason}
          onChange={(event) => setReason(event.target.value)}
        />
      </ConfirmationDialog>
    </div>
  );
}
