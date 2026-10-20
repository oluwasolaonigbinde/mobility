"use client";
import { useActionState } from "react";
import { Button } from "@/components/ui/button";
import { Field } from "@/components/ui/field";
import { Panel } from "@/components/ui/panel";
import {
  submitDriverApplicationAction,
  requestDriverOnboardingAccessAction,
  type DriverApplicationState,
  type DriverOnboardingAccessState,
} from "./actions";

export function DriverApplicationForms() {
  const [state, action, pending] = useActionState(
    submitDriverApplicationAction,
    {} as DriverApplicationState,
  );
  return (
    <>
      <Panel className="mt-5 p-6">
        <h2 className="font-display text-2xl font-semibold">Your contact details</h2>
        {state.submitted ? (
          <p role="status" className="text-green mt-4 text-sm">
            Thanks — we’ve got your application. Check your email for a link to the next step.
          </p>
        ) : (
          <form action={action} className="mt-5 grid gap-4" noValidate>
            <Field
              label="Full name"
              name="full_name"
              autoComplete="name"
              required
              error={state.fieldErrors?.full_name}
            />
            <Field
              label="Email"
              name="email"
              type="email"
              autoComplete="email"
              required
              error={state.fieldErrors?.email}
            />
            <div className="grid gap-4 sm:grid-cols-2">
              <Field
                label="Phone (optional)"
                name="phone"
                type="tel"
                autoComplete="tel"
                error={state.fieldErrors?.phone}
              />
              <Field
                label="City you drive in"
                name="service_city"
                autoComplete="address-level2"
                required
                maxLength={128}
                error={state.fieldErrors?.service_city}
              />
            </div>
            <input type="hidden" name="country_code" value="NG" />
            {state.error ? (
              <p role="alert" className="text-coral text-sm">
                {state.error}
              </p>
            ) : null}
            <Button type="submit" disabled={pending}>
              {pending ? "Sending…" : "Send application"}
            </Button>
          </form>
        )}
      </Panel>
      <details id="application-link" className="border-edge mt-5 rounded-xl border p-5">
        <summary className="text-green cursor-pointer text-sm">
          Check your application or get a new link
        </summary>
        <NewCodePanel />
      </details>
    </>
  );
}

export function NewCodePanel() {
  const [state, action, pending] = useActionState(
    requestDriverOnboardingAccessAction,
    {} as DriverOnboardingAccessState,
  );
  return (
    <div className="mt-5">
      <h2 className="font-display text-xl font-semibold">Continue your application</h2>
      <p className="text-muted mt-2 text-sm">
        Enter the email you applied with. We’ll send a link to your current step if your application
        is still open.
      </p>
      <form
        action={action}
        className="mt-4 grid gap-4 sm:grid-cols-[1fr_auto] sm:items-end"
        noValidate
      >
        <Field
          label="Email you applied with"
          name="email"
          type="email"
          autoComplete="email"
          defaultValue={state.email}
          required
        />
        <Button type="submit" variant="ghost" disabled={pending}>
          {pending ? "Sending…" : "Email me a link"}
        </Button>
        {state.error ? (
          <p role="alert" className="text-coral text-sm sm:col-span-2">
            {state.error}
          </p>
        ) : null}
        {state.done ? (
          <p role="status" className="text-green text-sm sm:col-span-2">
            {state.done}
          </p>
        ) : null}
      </form>
    </div>
  );
}
