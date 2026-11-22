"use client";

import Link from "next/link";
import { useActionState } from "react";
import { Button } from "@/components/ui/button";
import { Field } from "@/components/ui/field";
import { completeDriverAccountSetupAction, type DriverAccountSetupState } from "./actions";

const initialState: DriverAccountSetupState = {};

export function DriverAccountSetupForm({ token }: { token: string }) {
  const [state, action, pending] = useActionState(completeDriverAccountSetupAction, initialState);

  if (state.done)
    return (
      <div
        role="status"
        className="border-green/40 bg-green/10 text-green rounded-lg border p-3 text-sm"
      >
        <p>{state.done}</p>
        <Link href="/login" className="mt-2 inline-block underline">
          Continue to sign in
        </Link>
      </div>
    );

  return (
    <form action={action} className="flex flex-col gap-5" noValidate>
      <input type="hidden" name="token" value={token} />
      <Field
        label="New password"
        name="new_password"
        type="password"
        autoComplete="new-password"
        minLength={12}
        required
      />
      <Field
        label="Confirm new password"
        name="confirm_password"
        type="password"
        autoComplete="new-password"
        minLength={12}
        required
      />
      {state.error ? (
        <p
          role="alert"
          className="border-coral/40 bg-coral/10 text-coral rounded-lg border p-3 text-sm"
        >
          {state.error}
        </p>
      ) : null}
      <Button type="submit" disabled={pending} className="w-full">
        {pending ? "Setting password…" : "Set password"}
      </Button>
    </form>
  );
}
