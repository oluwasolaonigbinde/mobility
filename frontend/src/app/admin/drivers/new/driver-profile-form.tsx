"use client";

import { useActionState } from "react";
import { createDriverProfileAction, type AdminActionState } from "../../fleet-actions";
import { Button } from "@/components/ui/button";
import { Field } from "@/components/ui/field";

const initialState: AdminActionState = {};

export function DriverProfileForm({ users }: { users: Array<{ id: string; label: string }> }) {
  const [state, formAction, pending] = useActionState(createDriverProfileAction, initialState);

  return (
    <form action={formAction} className="flex flex-col gap-5" noValidate>
      <div className="flex flex-col gap-1.5">
        <label htmlFor="dp-user" className="micro text-muted">
          Driver user
        </label>
        <select
          id="dp-user"
          name="user_id"
          required
          defaultValue=""
          className="border-edge bg-raised text-ink focus:border-amber h-11 rounded-lg border px-3.5 text-sm focus:outline-none"
        >
          <option value="" disabled>
            Select a driver-role user…
          </option>
          {users.map((u) => (
            <option key={u.id} value={u.id}>
              {u.label}
            </option>
          ))}
        </select>
      </div>

      <Field label="Licence number" name="license_number" placeholder="e.g. ABJ-DL-042931" />
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Service city" name="service_city" placeholder="e.g. Abuja" />
        <Field
          label="Country code"
          name="country_code"
          placeholder="NG"
          maxLength={2}
          className="font-mono uppercase"
        />
      </div>

      {state.error ? (
        <p
          role="alert"
          className="border-coral/40 bg-coral/10 text-coral rounded-lg border px-3.5 py-2.5 text-sm"
        >
          {state.error}
        </p>
      ) : null}

      <Button type="submit" disabled={pending} className="w-full">
        {pending ? "Creating…" : "Create profile (approved)"}
      </Button>
    </form>
  );
}
