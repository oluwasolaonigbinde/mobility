"use client";

import { useActionState, useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { ConfirmationDialog } from "@/components/ui/confirmation-dialog";
import { initiateDriverAccountSetupAction, type DriverAccountSetupState } from "./actions";

const initialState: DriverAccountSetupState = {};

export function AccountSetupAction({
  applicationId,
  applicantName,
}: {
  applicationId: string;
  applicantName: string;
}) {
  const [state, action, pending] = useActionState(initiateDriverAccountSetupAction, initialState);
  const [confirming, setConfirming] = useState(false);
  const [clientRequestId] = useState(() => crypto.randomUUID());
  const triggerRef = useRef<HTMLButtonElement>(null);
  const actionFormRef = useRef<HTMLFormElement>(null);
  const statusRef = useRef<HTMLParagraphElement>(null);

  useEffect(() => {
    if (state.done) statusRef.current?.focus();
  }, [state.done]);

  if (state.done) {
    return (
      <p ref={statusRef} role="status" tabIndex={-1} className="text-green text-sm outline-none">
        {state.done}
      </p>
    );
  }

  return (
    <div>
      <Button ref={triggerRef} type="button" onClick={() => setConfirming(true)} disabled={pending}>
        Start account setup
      </Button>
      <form ref={actionFormRef} action={action} className="hidden" aria-hidden="true">
        <input type="hidden" name="application_id" value={applicationId} />
        <input type="hidden" name="client_request_id" value={clientRequestId} />
      </form>
      <ConfirmationDialog
        open={confirming}
        onOpenChange={setConfirming}
        title={`Start account setup for ${applicantName}?`}
        description="This creates a one-use setup link and queues delivery to the applicant's stored email. Delivery is not confirmed. It replaces any earlier unused setup link."
        cancelLabel="Keep current setup state"
        confirmLabel="Create one-use setup link"
        onConfirm={() => actionFormRef.current?.requestSubmit()}
        returnFocusRef={triggerRef}
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
