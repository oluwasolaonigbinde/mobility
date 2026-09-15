"use client";

import { useActionState, useState } from "react";
import { Button } from "@/components/ui/button";
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

  if (state.done) {
    return (
      <p role="status" className="text-green text-sm">
        {state.done}
      </p>
    );
  }

  return (
    <div>
      <Button type="button" onClick={() => setConfirming(true)} disabled={pending}>
        Start account setup
      </Button>
      {confirming ? (
        <div
          role="alertdialog"
          aria-label={`Start account setup for ${applicantName}?`}
          className="border-amber bg-raised mt-3 rounded-lg border p-4"
          onKeyDown={(event) => {
            if (event.key === "Escape") setConfirming(false);
          }}
        >
          <p className="font-medium">Start account setup for {applicantName}?</p>
          <p className="text-muted mt-1 text-sm">
            A one-use link will be sent to the applicant&apos;s stored email. This replaces any
            earlier unused setup link.
          </p>
          <form action={action} className="mt-3 flex flex-col gap-2 sm:flex-row">
            <input type="hidden" name="application_id" value={applicationId} />
            <input type="hidden" name="client_request_id" value={clientRequestId} />
            <Button type="button" variant="ghost" autoFocus onClick={() => setConfirming(false)}>
              Keep current setup state
            </Button>
            <Button type="submit" disabled={pending}>
              {pending ? "Starting…" : "Issue one-use setup link"}
            </Button>
          </form>
        </div>
      ) : null}
      {state.error ? (
        <p role="alert" className="text-coral mt-2 text-sm">
          {state.error}
        </p>
      ) : null}
    </div>
  );
}
