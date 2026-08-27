"use client";

import { useActionState } from "react";
import { Button } from "@/components/ui/button";
import { Field } from "@/components/ui/field";
import { Panel } from "@/components/ui/panel";
import {
  checkDriverApplicationStatusAction,
  submitDriverApplicationAction,
  type DriverApplicationState,
  type DriverApplicationStatusState,
} from "./actions";
import { PersonPayeeForm } from "./person-payee-form";
import { VehicleForm } from "./vehicle-form";

const initialApplicationState: DriverApplicationState = {};
const initialStatusState: DriverApplicationStatusState = {};

export function DriverApplicationForms() {
  const [applicationState, submitAction, submitting] = useActionState(
    submitDriverApplicationAction,
    initialApplicationState,
  );
  const [statusState, checkStatusAction, checking] = useActionState(
    checkDriverApplicationStatusAction,
    initialStatusState,
  );
  return (
    <div>
      <div className="grid gap-5 lg:grid-cols-[1.2fr_0.8fr]">
        <Panel className="p-6">
          <p className="micro text-amber mb-2">Driver network</p>
          <h2 className="font-display text-2xl font-semibold">Start an application</h2>
          <p className="text-muted mt-2 mb-6 text-sm">
            Share the minimum contact details. An operations reviewer will contact you if the cohort
            is accepting applications.
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
                label="Phone"
                name="phone"
                type="tel"
                autoComplete="tel"
                error={applicationState.fieldErrors?.phone}
              />
              <Field
                label="Service city"
                name="service_city"
                autoComplete="address-level2"
                error={applicationState.fieldErrors?.service_city}
              />
            </div>
            <Field
              label="Country code"
              name="country_code"
              placeholder="NG"
              maxLength={2}
              error={applicationState.fieldErrors?.country_code}
            />
            {applicationState.error ? (
              <p
                role="alert"
                className="border-coral/40 bg-coral/10 text-coral rounded-lg border px-3.5 py-2.5 text-sm"
              >
                {applicationState.error}
              </p>
            ) : null}
            {applicationState.submitted ? (
              <div
                role="status"
                className="border-green/40 bg-green/10 text-green rounded-lg border px-3.5 py-2.5 text-sm"
              >
                <p>Application received for review.</p>
                <p className="text-ink mt-2">
                  Check the application email for an expiring onboarding access code.
                </p>
                {applicationState.reference ? (
                  <p className="text-ink mt-2">
                    Save this status reference:{" "}
                    <code className="font-mono">{applicationState.reference}</code>
                  </p>
                ) : null}
              </div>
            ) : null}
            <Button type="submit" disabled={submitting}>
              {submitting ? "Sending…" : "Submit application"}
            </Button>
          </form>
        </Panel>

        <Panel className="p-6">
          <p className="micro text-cyan mb-2">Application status</p>
          <h2 className="font-display text-2xl font-semibold">Check your reference</h2>
          <p className="text-muted mt-2 mb-6 text-sm">
            Status responses are intentionally limited to the pending review state.
          </p>
          <form action={checkStatusAction} className="flex flex-col gap-4">
            <Field label="Application reference" name="reference" required />
            {statusState.error ? (
              <p
                role="alert"
                className="border-coral/40 bg-coral/10 text-coral rounded-lg border px-3.5 py-2.5 text-sm"
              >
                {statusState.error}
              </p>
            ) : null}
            {statusState.pending ? (
              <p
                role="status"
                className="border-amber/40 bg-amber/10 text-amber rounded-lg border px-3.5 py-2.5 text-sm"
              >
                Application status: pending review. Person/payee stage:{" "}
                {statusState.personPayeeStatus}. Vehicle stage: {statusState.vehicleStatus}.
              </p>
            ) : null}
            <Button type="submit" variant="ghost" disabled={checking}>
              {checking ? "Checking…" : "Check status"}
            </Button>
          </form>
        </Panel>
      </div>
      <PersonPayeeForm />
      <VehicleForm />
    </div>
  );
}
