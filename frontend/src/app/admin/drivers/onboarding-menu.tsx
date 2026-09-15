"use client";

import { useRef, useState, useTransition } from "react";
import { updateDriverOnboardingAction } from "../fleet-actions";
import type { components } from "@/lib/api/schema";
import { ConfirmationDialog } from "@/components/ui/confirmation-dialog";

type Onboarding = components["schemas"]["DriverOnboardingStatus"];

/** Context-sensitive next steps for driver trust state. */
const steps: Record<Onboarding, Array<{ to: Onboarding; label: string; danger?: boolean }>> = {
  pending: [
    { to: "active", label: "Approve" },
    { to: "rejected", label: "Reject", danger: true },
  ],
  active: [{ to: "suspended", label: "Suspend", danger: true }],
  suspended: [{ to: "active", label: "Reinstate" }],
  rejected: [{ to: "pending", label: "Re-review" }],
};

export function DriverOnboardingMenu({
  driverProfileId,
  driverName,
  status,
}: {
  driverProfileId: string;
  driverName: string;
  status: Onboarding;
}) {
  const [pending, startTransition] = useTransition();
  const [error, setError] = useState<string>();
  const [confirming, setConfirming] = useState<Onboarding>();
  const triggerRef = useRef<HTMLButtonElement>(null);

  function run(to: Onboarding, danger?: boolean, confirmed = false) {
    if (danger && !confirmed) {
      setConfirming(to);
      return;
    }
    setConfirming(undefined);
    setError(undefined);
    startTransition(async () => {
      const result = await updateDriverOnboardingAction({ driverProfileId, status: to });
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
        title={`${confirming === "suspended" ? "Suspend" : "Reject"} ${driverName}?`}
        description={
          confirming === "suspended"
            ? "The driver will no longer be able to start campaign work."
            : "The application will leave the active review queue."
        }
        cancelLabel={confirming === "suspended" ? "Keep driver active" : "Keep pending"}
        confirmLabel={`Confirm ${confirming === "suspended" ? "suspension" : "rejection"}`}
        onConfirm={() => {
          if (confirming) run(confirming, true, true);
        }}
        returnFocusRef={triggerRef}
        pending={pending}
      />
    </div>
  );
}
