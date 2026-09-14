"use client";

import Link from "next/link";
import { useActionState, useEffect } from "react";
import { Button } from "@/components/ui/button";
import { Field } from "@/components/ui/field";
import { completeDriverAccountSetupAction, type DriverAccountSetupState } from "./actions";

const initialState: DriverAccountSetupState = {};

export function DriverAccountSetupForm({ token }: { token: string }) {
  const [state, action, pending] = useActionState(completeDriverAccountSetupAction, initialState);

  useEffect(() => {
    window.history.replaceState(null, "", "/driver-account-setup");
  }, []);

  return (
    <form action={action} className="flex flex-col gap-5" noValidate>
      {!state.done ? <input type="hidden" name="token" value={token} /> : null}
      <Field
        label="New password"
        name="new_password"
        type="password"
        autoComplete="new-password"
        minLength={12}
        required
        disabled={Boolean(state.done)}
      />
      <Field
        label="Confirm new password"
        name="confirm_password"
        type="password"
        autoComplete="new-password"
        minLength={12}
        required
        disabled={Boolean(state.done)}
      />
      {state.error ? (
        <p
          role="alert"
          className="border-coral/40 bg-coral/10 text-coral rounded-lg border p-3 text-sm"
        >
          {state.error}
        </p>
      ) : null}
      {state.done ? (
        <div
          role="status"
          className="border-green/40 bg-green/10 text-green rounded-lg border p-3 text-sm"
        >
          <p>{state.done}</p>
          <Link href="/login" className="mt-2 inline-block underline">
            Continue to sign in
          </Link>
        </div>
      ) : (
        <Button type="submit" disabled={pending} className="w-full">
          {pending ? "Setting password…" : "Set password"}
        </Button>
      )}
    </form>
  );
}
