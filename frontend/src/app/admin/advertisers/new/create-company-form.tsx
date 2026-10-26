"use client";

import { useActionState } from "react";
import { Button } from "@/components/ui/button";
import { Field } from "@/components/ui/field";
import { createCompanyAction, type CreateCompanyState } from "./actions";

export function CreateCompanyForm() {
  const [state, action, pending] = useActionState(createCompanyAction, {} as CreateCompanyState);
  return (
    <form action={action} className="flex flex-col gap-5">
      <Field label="Company name" name="name" required maxLength={255} />
      <Field label="Login email" name="email" type="email" required autoComplete="off" />
      <Field
        label="Currency"
        name="currency"
        placeholder="NGN"
        maxLength={3}
        className="uppercase"
      />
      <p className="text-muted text-sm">
        We&apos;ll email a one-time link to set a password. It works for 24 hours.
      </p>
      {state.error ? (
        <p role="alert" className="text-coral text-sm">
          {state.error}
        </p>
      ) : null}
      <Button type="submit" disabled={pending}>
        {pending ? "Sending…" : "Add company and send invite"}
      </Button>
    </form>
  );
}
