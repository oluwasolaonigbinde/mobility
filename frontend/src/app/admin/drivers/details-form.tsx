"use client";
import { useActionState } from "react";
import { Field } from "@/components/ui/field";
import { Button } from "@/components/ui/button";
import { updateDriverDetailsAction, type AdminActionState } from "../fleet-actions";
import type { components } from "@/lib/api/schema";

export function DriverDetailsForm({
  driver,
}: {
  driver: components["schemas"]["AdminDriverProfileRead"];
}) {
  const [state, action, pending] = useActionState(
    updateDriverDetailsAction,
    {} as AdminActionState,
  );
  return (
    <form action={action} className="mt-4 grid gap-4 sm:grid-cols-2">
      <input type="hidden" name="driver_profile_id" value={driver.id} />
      <Field
        label="Service city"
        name="service_city"
        defaultValue={driver.service_city ?? ""}
        maxLength={128}
      />
      <Field
        label="Country code"
        name="country_code"
        defaultValue={driver.country_code ?? ""}
        maxLength={2}
      />
      <Field
        label="Licence number"
        name="license_number"
        defaultValue={driver.license_number ?? ""}
        maxLength={128}
      />
      <div className="sm:col-span-2">
        <Button disabled={pending}>{pending ? "Saving…" : "Save details"}</Button>
      </div>
      {state.error ? (
        <p role="alert" className="text-coral sm:col-span-2">
          {state.error}
        </p>
      ) : null}
      {state.saved ? (
        <p role="status" className="text-green sm:col-span-2">
          Driver details saved.
        </p>
      ) : null}
    </form>
  );
}
