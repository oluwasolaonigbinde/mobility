"use client";

import { useActionState } from "react";
import { Field } from "@/components/ui/field";
import { Button } from "@/components/ui/button";
import { sendLoginInviteAction, type InviteState } from "./invite-actions";

export function LoginInviteForm({
  organizationId,
  email,
}: {
  organizationId: string;
  email?: string | null;
}) {
  const [state, action, pending] = useActionState(
    sendLoginInviteAction.bind(null, organizationId),
    {} as InviteState,
  );
  return (
    <form action={action} className="mb-5 grid max-w-md gap-3">
      <p className="text-muted text-sm">
        Send a login invite so this company can choose a password. Sending again replaces its
        earlier invite.
      </p>
      <Field name="email" label="Login email" type="email" defaultValue={email ?? ""} required />
      <Button type="submit" disabled={pending}>
        {pending ? "Sending…" : "Send login invite"}
      </Button>
      {state.error ? (
        <p role="alert" className="text-coral text-sm">
          {state.error}
        </p>
      ) : null}
      {state.done ? (
        <p role="status" className="text-green text-sm">
          {state.done}
        </p>
      ) : null}
    </form>
  );
}
