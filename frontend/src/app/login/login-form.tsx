"use client";

import { useActionState } from "react";
import { demoLoginAction, loginAction, type LoginState } from "./actions";
import { Button } from "@/components/ui/button";
import { Field } from "@/components/ui/field";
import type { DemoLoginRole } from "./demo-role";

const initialState: LoginState = {};

export function LoginForm({ demoLoginRole }: { demoLoginRole?: DemoLoginRole }) {
  const action = demoLoginRole ? demoLoginAction.bind(null, demoLoginRole) : loginAction;
  const [state, formAction, pending] = useActionState(action, initialState);

  if (demoLoginRole) {
    return (
      <form action={formAction} className="flex flex-col gap-5">
        {state.error ? (
          <p
            role="alert"
            className="border-coral/40 bg-coral/10 text-coral rounded-lg border px-3.5 py-2.5 text-sm"
          >
            {state.error}
          </p>
        ) : null}
        <Button type="submit" disabled={pending} className="w-full">
          {pending ? "Signing in…" : "Sign in"}
        </Button>
      </form>
    );
  }

  return (
    <form action={formAction} className="flex flex-col gap-5" noValidate>
      <Field
        label="Email"
        name="email"
        type="email"
        autoComplete="email"
        placeholder="you@company.com"
        required
        error={state.fieldErrors?.email}
      />
      <Field
        label="Password"
        name="password"
        type="password"
        autoComplete="current-password"
        placeholder="••••••••••••"
        required
        error={state.fieldErrors?.password}
      />
      {state.error ? (
        <p
          role="alert"
          className="border-coral/40 bg-coral/10 text-coral rounded-lg border px-3.5 py-2.5 text-sm"
        >
          {state.error}
        </p>
      ) : null}
      <Button type="submit" disabled={pending} className="mt-1 w-full">
        {pending ? "Signing in…" : "Enter the network"}
      </Button>
    </form>
  );
}
