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
        defaultValue={defaults.service_city}
        placeholder="e.g. Abuja"
      />
      <Field
        label="Country code"
        name="country_code"
        defaultValue={defaults.country_code}
        placeholder="NG"
        maxLength={2}
        className="uppercase"
      />
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
