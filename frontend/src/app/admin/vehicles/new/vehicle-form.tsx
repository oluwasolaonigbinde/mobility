"use client";

import { useActionState } from "react";
import { createVehicleAction, type AdminActionState } from "../../fleet-actions";
import { Button } from "@/components/ui/button";
import { Field } from "@/components/ui/field";

const initialState: AdminActionState = {};

const TYPES = ["car", "van", "minibus", "bus", "motorcycle", "tricycle", "other"] as const;

export function VehicleForm({ users }: { users: Array<{ id: string; label: string }> }) {
  const [state, formAction, pending] = useActionState(createVehicleAction, initialState);

  const selectClass =
    "h-11 rounded-lg border border-edge bg-raised px-3.5 text-sm text-ink transition-colors focus:border-amber focus:outline-none";

  return (
    <form action={formAction} className="flex flex-col gap-5" noValidate>
      <div className="flex flex-col gap-1.5">
        <label htmlFor="v-user" className="micro text-muted">
          Driver user
        </label>
        <select id="v-user" name="user_id" required defaultValue="" className={selectClass}>
          <option value="" disabled>
            Select the owning driver…
          </option>
          {users.map((u) => (
            <option key={u.id} value={u.id}>
              {u.label}
            </option>
          ))}
        </select>
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
        <Field
          label="Plate number"
          name="plate_number"
          required
          placeholder="ABC-482-KJ"
          className="font-mono uppercase"
        />
        <Field
          label="Plate country"
          name="plate_country_code"
          defaultValue="NG"
          maxLength={2}
          className="font-mono uppercase"
        />
      </div>

      <div className="flex flex-col gap-1.5">
        <label htmlFor="v-type" className="micro text-muted">
          Vehicle type
        </label>
        <select id="v-type" name="vehicle_type" defaultValue="car" className={selectClass}>
          {TYPES.map((t) => (
            <option key={t} value={t} className="capitalize">
              {t}
            </option>
          ))}
        </select>
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Make" name="make" placeholder="Toyota" />
        <Field label="Model" name="model" placeholder="Corolla" />
        <Field label="Year" name="year" inputMode="numeric" placeholder="2019" />
        <Field label="Color" name="color" placeholder="Silver" />
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
        {pending ? "Registering…" : "Register vehicle (active)"}
      </Button>
    </form>
  );
}
