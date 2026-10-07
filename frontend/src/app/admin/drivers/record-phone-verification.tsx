"use client";
import { useActionState, useState } from "react";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Field } from "@/components/ui/field";
import {
  recordPhoneVerificationAction,
  type PhoneVerificationState,
} from "./phone-verification-actions";

export function RecordPhoneVerification({
  driverId,
  challengeId,
}: {
  driverId: string;
  challengeId: string;
}) {
  const router = useRouter();
  const [state, action, pending] = useActionState(
    recordPhoneVerificationAction,
    {} as PhoneVerificationState,
  );
  const [open, setOpen] = useState(false);
  return (
    <div className="mt-4">
      {!open ? (
        <Button onClick={() => setOpen(true)}>Record phone verification</Button>
      ) : (
        <form action={action} className="flex max-w-md flex-col gap-3">
          <input type="hidden" name="driver_profile_id" value={driverId} />
          <input type="hidden" name="challenge_id" value={challengeId} />
          <p className="text-muted text-sm">
            Enter the code and sender number from the message Terrax received.
          </p>
          <Field
            name="code"
            label="Code received"
            type="password"
            inputMode="numeric"
            minLength={6}
            maxLength={6}
            autoComplete="off"
            required
          />
          <Field
            name="sender_phone"
            label="Sender phone number, including country code"
            type="tel"
            autoComplete="off"
            required
          />
          <Button type="submit" disabled={pending || Boolean(state.done)}>
            {pending ? "Checking…" : "Record verification"}
          </Button>
          {state.error ? (
            <p role="alert" className="text-coral text-sm">
              {state.error}
            </p>
          ) : null}
          {state.done ? (
            <div>
              <p role="status" className="text-green text-sm">
                {state.done}
              </p>
              <Button type="button" variant="ghost" onClick={() => router.refresh()}>
                Refresh phone status
              </Button>
            </div>
          ) : null}
        </form>
      )}
    </div>
  );
}
