"use client";

import { useActionState } from "react";
import { updateProfileAction, type DriverActionState } from "@/app/driver/actions";
import { Button } from "@/components/ui/button";
import { Field } from "@/components/ui/field";

const initialState: DriverActionState = {};

export function ProfileForm({
  defaults,
}: {
  defaults: { license_number: string; service_city: string; country_code: string };
}) {
  const [state, formAction, pending] = useActionState(updateProfileAction, initialState);

  return (
    <form action={formAction} className="flex flex-col gap-4">
      <Field
        label="Licence number"
        name="license_number"
        defaultValue={defaults.license_number}
        placeholder="e.g. ABJ-DL-042931"
        autoComplete="off"
      />
      <Field
        label="Service city"
        name="service_city"
        required
        maxLength={128}
        defaultValue={defaults.service_city}
        placeholder="e.g. Abuja"
      />
      <input type="hidden" name="country_code" value={defaults.country_code || "NG"} />
      {state.error ? (
        <p role="alert" className="text-coral text-xs">
          {state.error}
        </p>
      ) : null}
      <Button type="submit" disabled={pending} className="h-12 w-full">
        {pending ? "Saving…" : "Save details"}
      </Button>
    </form>
  );
}
