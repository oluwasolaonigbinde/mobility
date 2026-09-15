"use client";

import { useState, useTransition } from "react";
import { updateDriverOnboardingAction } from "../fleet-actions";
import type { components } from "@/lib/api/schema";

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
          aria-labelledby="driver-status-confirmation-title"
          className="bg-bg/80 fixed inset-0 z-50 grid place-items-center p-4 text-left backdrop-blur-sm"
          onKeyDown={(event) => {
            if (event.key === "Escape") setConfirming(undefined);
          }}
        >
          <div className="border-coral/40 bg-panel w-full max-w-sm rounded-xl border p-5 shadow-xl">
            <h2
              id="driver-status-confirmation-title"
              className="font-display text-lg font-semibold"
            >
              {confirming === "suspended" ? "Suspend" : "Reject"} {driverName}?
            </h2>
            <p className="text-muted mt-2 text-sm">
              {confirming === "suspended"
                ? "The driver will no longer be able to start campaign work."
                : "The application will leave the active review queue."}
            </p>
            <div className="mt-5 flex flex-col gap-2 sm:flex-row sm:justify-end">
              <button type="button" autoFocus onClick={() => setConfirming(undefined)}>
                {confirming === "suspended" ? "Keep driver active" : "Keep pending"}
              </button>
              <button
                type="button"
                className="text-coral"
                onClick={() => run(confirming, true, true)}
              >
                Confirm {confirming === "suspended" ? "suspension" : "rejection"}
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
