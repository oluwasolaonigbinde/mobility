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

export function VehicleStatusMenu({ vehicleId, status }: { vehicleId: string; status: VStatus }) {
  const [pending, startTransition] = useTransition();
  const [error, setError] = useState<string>();

  function run(to: VStatus, danger?: boolean) {
    if (danger && !window.confirm("Suspend this vehicle? Its campaigns stop billing.")) return;
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
    </div>
  );
}
