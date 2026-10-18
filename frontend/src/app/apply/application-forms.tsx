"use client";

import { useActionState } from "react";
import { Button } from "@/components/ui/button";
import { Field } from "@/components/ui/field";
import { Panel } from "@/components/ui/panel";
import { cx } from "@/lib/cx";
import {
  checkDriverApplicationStatusAction,
  requestDriverOnboardingAccessAction,
  submitDriverApplicationAction,
  type DriverApplicationState,
  type DriverApplicationStatusState,
  type DriverOnboardingAccessState,
} from "./actions";
import { presentApplicationStage } from "./application-status";

const initialApplicationState: DriverApplicationState = {};
const initialStatusState: DriverApplicationStatusState = {};
const initialOnboardingAccessState: DriverOnboardingAccessState = {};

const alertClass = "border-coral/40 bg-coral/10 text-coral rounded-lg border px-3.5 py-2.5 text-sm";
const doneClass = "border-green/40 bg-green/10 text-green rounded-lg border px-3.5 py-2.5 text-sm";

export function DriverApplicationForms() {
  const [applicationState, submitAction, submitting] = useActionState(
    submitDriverApplicationAction,
    initialApplicationState,
  );
  const [statusState, checkStatusAction, checking] = useActionState(
    checkDriverApplicationStatusAction,
    initialStatusState,
  );
  const personPayee = presentApplicationStage(statusState.personPayeeStatus);
  const vehicle = presentApplicationStage(statusState.vehicleStatus);
  return (
    <div>
      <div className="grid gap-5 lg:grid-cols-[1.2fr_0.8fr]">
        <Panel className="p-6">
          <h2 className="font-display text-2xl font-semibold">Your contact details</h2>
          <p className="text-muted mt-2 mb-6 text-sm">
            Tell us who you are. We&apos;ll email you a code for the next step.
          </p>
          <form action={submitAction} className="flex flex-col gap-4" noValidate>
            <Field
              label="Full name"
              name="full_name"
              autoComplete="name"
              required
              error={applicationState.fieldErrors?.full_name}
            />
            <Field
              label="Email"
              name="email"
              type="email"
              autoComplete="email"
              required
              error={applicationState.fieldErrors?.email}
            />
            <div className="grid gap-4 sm:grid-cols-2">
              <Field
                label="Phone (optional)"
                name="phone"
                type="tel"
                autoComplete="tel"
                error={applicationState.fieldErrors?.phone}
              />
              <Field
                label="City you drive in"
                name="service_city"
                autoComplete="address-level2"
                required
                maxLength={128}
                error={applicationState.fieldErrors?.service_city}
              />
            </div>
            <Field
              label="Country code (optional)"
              name="country_code"
              placeholder="NG"
              maxLength={2}
              error={applicationState.fieldErrors?.country_code}
            />
            {applicationState.error ? (
              <p role="alert" className={alertClass}>
                {applicationState.error}
              </p>
            ) : null}
            {applicationState.submitted ? (
              <div role="status" className={doneClass}>
                <p>
                  Thanks — we&apos;ve got your application. We&apos;ve emailed you a code for the
                  next step.
                </p>
                {applicationState.reference ? (
                  <p className="text-ink mt-2">
                    Keep this reference to check your status:{" "}
                    <code className="font-mono break-all">{applicationState.reference}</code>
                  </p>
                ) : null}
              </div>
            ) : null}
            <Button type="submit" disabled={submitting}>
              {submitting ? "Sending…" : "Send application"}
            </Button>
          </form>
        </Panel>

        <Panel className="p-6">
          <h2 className="font-display text-2xl font-semibold">Check application status</h2>
          <form action={checkStatusAction} className="mt-6 flex flex-col gap-4">
            <Field
              label="Application reference"
              name="reference"
              required
              aria-describedby="application-reference-hint"
            />
            <p id="application-reference-hint" className="text-muted -mt-2 text-xs">
              Use the reference you got when you applied.
            </p>
            {statusState.error ? (
              <p role="alert" className={alertClass}>
                {statusState.error}
              </p>
            ) : null}
            {statusState.pending ? (
              <div
                role="status"
                className="border-amber/40 bg-amber/10 rounded-lg border px-3.5 py-2.5 text-sm"
              >
                <p className="text-ink font-medium">Your application</p>
                <dl className="text-ink mt-3 grid gap-3">
                  <div>
                    <dt className="text-muted text-xs font-medium">ID and bank details</dt>
                    <dd className={cx("mt-1 font-medium", personPayee.tone)}>
                      {personPayee.label}
                    </dd>
                    <dd className="text-muted mt-1 text-xs leading-5">{personPayee.detail}</dd>
                  </div>
                  <div>
                    <dt className="text-muted text-xs font-medium">Car</dt>
                    <dd className={cx("mt-1 font-medium", vehicle.tone)}>{vehicle.label}</dd>
                    <dd className="text-muted mt-1 text-xs leading-5">{vehicle.detail}</dd>
                  </div>
                </dl>
              </div>
            ) : null}
            <Button type="submit" variant="ghost" disabled={checking}>
              {checking ? "Checking…" : "Check status"}
            </Button>
          </form>
        </Panel>
      </div>
      <NewCodePanel />
    </div>
  );
}

/** Lets an applicant whose emailed code has stopped working ask for a new one. */
export function NewCodePanel() {
  const [state, action, requesting] = useActionState(
    requestDriverOnboardingAccessAction,
    initialOnboardingAccessState,
  );
  return (
    <Panel className="mt-5 p-6">
      <h2 className="font-display text-2xl font-semibold">Code not working? Get a new one</h2>
      <p className="text-muted mt-2 mb-6 max-w-3xl text-sm">
        Enter the email you applied with and we&apos;ll send a new code if your application is still
        open.
      </p>
      <form
        action={action}
        className="grid items-end gap-4 sm:grid-cols-[minmax(0,1fr)_auto]"
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
        <Button type="submit" variant="ghost" disabled={requesting}>
          {requesting ? "Sending…" : "Send me a new code"}
        </Button>
        {state.error ? (
          <p role="alert" className={cx(alertClass, "sm:col-span-2")}>
            {state.error}
          </p>
        ) : null}
        {state.done ? (
          <p role="status" className={cx(doneClass, "sm:col-span-2")}>
            {state.done}
          </p>
        ) : null}
      </form>
    </Panel>
  );
}
