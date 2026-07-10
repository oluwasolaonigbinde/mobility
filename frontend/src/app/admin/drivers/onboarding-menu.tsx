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
  status,
}: {
  driverProfileId: string;
  status: Onboarding;
}) {
  const [pending, startTransition] = useTransition();
  const [error, setError] = useState<string>();

  function run(to: Onboarding, danger?: boolean) {
    if (danger && !window.confirm(`${to === "suspended" ? "Suspend" : "Reject"} this driver?`)) {
      return;
    }
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
    </div>
  );
}
