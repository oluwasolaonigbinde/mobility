"use client";

import { useRef, useState, useTransition } from "react";
import { updateVehicleStatusAction } from "../fleet-actions";
import type { components } from "@/lib/api/schema";
import { ConfirmationDialog } from "@/components/ui/confirmation-dialog";

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
  const triggerRef = useRef<HTMLButtonElement>(null);

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
            ref={s.danger ? triggerRef : undefined}
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
      <ConfirmationDialog
        open={Boolean(confirming)}
        onOpenChange={(open) => {
          if (!open) setConfirming(undefined);
        }}
        title={`Suspend ${vehicleLabel}?`}
        description="Campaign activity for this vehicle will stop immediately."
        cancelLabel="Keep vehicle active"
        confirmLabel="Confirm suspension"
        onConfirm={() => {
          if (confirming) run(confirming, true, true);
        }}
        returnFocusRef={triggerRef}
        pending={pending}
      />
    </div>
  );
}
