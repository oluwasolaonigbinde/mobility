"use client";

import { useActionState } from "react";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Field } from "@/components/ui/field";
import { completePasswordResetAction, type PasswordResetCompleteState } from "./actions";

const initialState: PasswordResetCompleteState = {};

export function PasswordResetForm({ token }: { token: string }) {
  const [state, action, pending] = useActionState(completePasswordResetAction, initialState);
  return (
    <form action={action} className="flex flex-col gap-5" noValidate>
      <input type="hidden" name="token" value={token} />
      <Field
        label="New password"
        name="new_password"
        type="password"
        autoComplete="new-password"
        required
      />
      <Field
        label="Confirm new password"
        name="confirm_password"
        type="password"
        autoComplete="new-password"
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
      ) : null}
      {!state.done ? (
        <Button type="submit" disabled={pending} className="w-full">
          {pending ? "Resetting…" : "Reset password"}
        </Button>
      ) : null}
    </form>
  );
}
