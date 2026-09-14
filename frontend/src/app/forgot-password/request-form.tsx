"use client";

import { useActionState } from "react";
import { Button } from "@/components/ui/button";
import { Field } from "@/components/ui/field";
import { requestPasswordResetAction, type PasswordResetRequestState } from "./actions";

const initialState: PasswordResetRequestState = {};

export function PasswordResetRequestForm() {
  const [state, action, pending] = useActionState(requestPasswordResetAction, initialState);
  return (
    <form action={action} className="flex flex-col gap-5" noValidate>
      <Field
        label="Email"
        name="email"
        type="email"
        autoComplete="email"
        defaultValue={state.email}
        placeholder="you@example.com"
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
        <p
          role="status"
          className="border-green/40 bg-green/10 text-green rounded-lg border p-3 text-sm"
        >
          {state.done}
        </p>
      ) : null}
      <Button type="submit" disabled={pending} className="w-full">
        {pending ? "Sending…" : "Send reset instructions"}
      </Button>
    </form>
  );
}
