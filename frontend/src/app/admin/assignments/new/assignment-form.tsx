"use client";

import { useActionState, useState } from "react";
import { createAssignmentAction, type AdminActionState } from "../actions";
import { Button } from "@/components/ui/button";
import { Field } from "@/components/ui/field";

const initialState: AdminActionState = {};

interface Option {
  id: string;
  label: string;
  driverProfileId?: string;
}

export function AssignmentForm({
  campaigns,
  drivers,
  vehicles,
}: {
  campaigns: Option[];
  drivers: Option[];
  vehicles: Option[];
}) {
  const [state, formAction, pending] = useActionState(createAssignmentAction, initialState);
  const [driverId, setDriverId] = useState("");

  // Only offer vehicles that belong to the selected driver — the backend
  // enforces this pairing; the UI just avoids the dead end.
  const driverVehicles = driverId
    ? vehicles.filter((v) => v.driverProfileId === driverId)
    : vehicles;

  const selectClass =
    "h-11 rounded-lg border border-edge bg-raised px-3.5 text-sm text-ink transition-colors focus:border-amber focus:outline-none";

  return (
    <form action={formAction} className="flex flex-col gap-5" noValidate>
      <div className="flex flex-col gap-1.5">
        <label htmlFor="a-campaign" className="micro text-muted">
          Campaign
        </label>
        <select id="a-campaign" name="campaign_id" required defaultValue="" className={selectClass}>
          <option value="" disabled>
            Select a campaign…
          </option>
          {campaigns.map((c) => (
            <option key={c.id} value={c.id}>
              {c.label}
            </option>
          ))}
        </select>
      </div>

      <div className="flex flex-col gap-1.5">
        <label htmlFor="a-driver" className="micro text-muted">
          Driver
        </label>
        <select
          id="a-driver"
          name="driver_profile_id"
          required
          value={driverId}
          onChange={(e) => setDriverId(e.target.value)}
          className={selectClass}
        >
          <option value="" disabled>
            Select a driver…
          </option>
          {drivers.map((d) => (
            <option key={d.id} value={d.id}>
              {d.label}
            </option>
          ))}
        </select>
      </div>

      <div className="flex flex-col gap-1.5">
        <label htmlFor="a-vehicle" className="micro text-muted">
          Vehicle {driverId ? `(${driverVehicles.length} for this driver)` : ""}
        </label>
        <select id="a-vehicle" name="vehicle_id" required defaultValue="" className={selectClass}>
          <option value="" disabled>
            Select a vehicle…
          </option>
          {driverVehicles.map((v) => (
            <option key={v.id} value={v.id}>
              {v.label}
            </option>
          ))}
        </select>
      </div>

      <Field label="Notes" name="notes" placeholder="Optional context for the driver" />

      {state.error ? (
        <p
          role="alert"
          className="border-coral/40 bg-coral/10 text-coral rounded-lg border px-3.5 py-2.5 text-sm"
        >
          {state.error}
        </p>
      ) : null}

      <Button type="submit" disabled={pending} className="w-full">
        {pending ? "Offering…" : "Send offer"}
      </Button>
    </form>
  );
}
