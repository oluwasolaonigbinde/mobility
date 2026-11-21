"use client";

import { startTransition, useActionState, useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { formatDateTime } from "@/lib/format";
import { ConfirmationDialog } from "@/components/ui/confirmation-dialog";
import { initiateDriverAccountSetupAction, type DriverAccountSetupState } from "./actions";

const initialState: DriverAccountSetupState = {};

export function AccountSetupAction({
  applicationId,
  applicantName,
  applicantEmail,
}: {
  applicationId: string;
  applicantName: string;
  applicantEmail: string;
}) {
  const [state, action, pending] = useActionState(initiateDriverAccountSetupAction, initialState);
  const [confirmationId, setConfirmationId] = useState<string>();
  const confirming = Boolean(confirmationId && confirmationId !== state.requestId);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const statusRef = useRef<HTMLParagraphElement>(null);

  useEffect(() => {
    if (state.requestId) statusRef.current?.focus();
  }, [state.requestId]);

  function sendLink() {
    if (!confirmationId) return;
    const data = new FormData();
    data.set("application_id", applicationId);
    data.set("client_request_id", confirmationId);
    startTransition(() => action(data));
  }

  return (
    <div>
      {state.requestedAt ? (
        <p
          ref={statusRef}
          role="status"
          tabIndex={-1}
          className="text-green mb-2 text-sm outline-none"
        >
          Setup email on its way to{" "}
          <span className="break-all" data-feedback-private>
            {applicantEmail}
          </span>{" "}
          (requested {formatDateTime(state.requestedAt)})
        </p>
      ) : null}
      <Button
        ref={triggerRef}
        type="button"
        onClick={() => setConfirmationId(crypto.randomUUID())}
        disabled={pending}
      >
        {state.requestedAt ? "Send another link" : "Start account setup"}
      </Button>
      <ConfirmationDialog
        open={confirming}
        onOpenChange={(open) => {
          if (!open) setConfirmationId(undefined);
        }}
        title={`Email ${applicantName} a link to set their password?`}
        description="A new link replaces any earlier unused setup link."
        cancelLabel="Cancel"
        confirmLabel="Send link"
        onConfirm={sendLink}
        returnFocusRef={
          state.requestId && state.requestId === confirmationId ? statusRef : triggerRef
        }
        pending={pending}
        error={state.error}
      />
      {!confirming && state.error ? (
        <p role="alert" className="text-coral mt-2 text-sm">
          {state.error}
        </p>
      ) : null}
    </div>
  );
}
