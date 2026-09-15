"use client";

import { useState, useTransition } from "react";
import { updateVehicleStatusAction } from "../fleet-actions";
import type { components } from "@/lib/api/schema";

type VStatus = components["schemas"]["VehicleStatus"];

const steps: Record<VStatus, Array<{ to: VStatus; label: string; danger?: boolean }>> = {
  pending: [{ to: "active", label: "Approve" }],
  active: [
    { to: "suspended", label: "Suspend", danger: true },
    { to: "inactive", label: "Retire" },
  ],
  suspended: [{ to: "active", label: "Reinstate" }],
  inactive: [{ to: "active", label: "Reactivate" }],
};

export function VehicleStatusMenu({
  vehicleId,
  vehicleLabel,
  status,
}: {
  vehicleId: string;
  vehicleLabel: string;
  status: VStatus;
}) {
  const [pending, startTransition] = useTransition();
  const [error, setError] = useState<string>();
  const [confirming, setConfirming] = useState<VStatus>();

  function run(to: VStatus, danger?: boolean, confirmed = false) {
    if (danger && !confirmed) {
      setConfirming(to);
      return;
    }
    setConfirming(undefined);
    setError(undefined);
    startTransition(async () => {
      const result = await updateVehicleStatusAction({ vehicleId, status: to });
      if (result.error) setError(result.error);
    });
  }

  return (
    <div className="flex flex-col items-end gap-1">
      <div className="flex gap-3">
        {steps[status].map((s) => (
          <button
            key={s.to}
            type="button"
            disabled={pending}
            onClick={() => run(s.to, s.danger)}
            className={
              "micro transition-colors disabled:opacity-50 " +
              (s.danger ? "text-muted hover:text-coral" : "text-muted hover:text-green")
            }
          >
            {pending ? "…" : s.label}
          </button>
        ))}
      </div>
      {error ? (
        <p role="alert" className="text-coral text-xs">
          {error}
        </p>
      ) : null}
      {confirming ? (
        <div
          role="alertdialog"
          aria-modal="true"
          aria-labelledby="vehicle-status-confirmation-title"
          className="bg-bg/80 fixed inset-0 z-50 grid place-items-center p-4 text-left backdrop-blur-sm"
          onKeyDown={(event) => {
            if (event.key === "Escape") setConfirming(undefined);
          }}
        >
          <div className="border-coral/40 bg-panel w-full max-w-sm rounded-xl border p-5 shadow-xl">
            <h2
              id="vehicle-status-confirmation-title"
              className="font-display text-lg font-semibold"
            >
              Suspend {vehicleLabel}?
            </h2>
            <p className="text-muted mt-2 text-sm">
              Campaign activity for this vehicle will stop immediately.
            </p>
            <div className="mt-5 flex flex-col gap-2 sm:flex-row sm:justify-end">
              <button type="button" autoFocus onClick={() => setConfirming(undefined)}>
                Keep vehicle active
              </button>
              <button
                type="button"
                className="text-coral"
                onClick={() => run(confirming, true, true)}
              >
                Confirm suspension
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
