"use client";

import { useState, useTransition } from "react";
import { assignmentAction } from "./actions";
import { Button } from "@/components/ui/button";
import type { components } from "@/lib/api/schema";

type Status = components["schemas"]["CampaignAssignmentStatus"];

/** One primary next step per status — a driver mid-traffic gets one button. */
const nextStep: Partial<
  Record<
    Status,
    {
      action: "accept" | "decline" | "deactivate";
      label: string;
      variant: "primary" | "ghost" | "danger";
    }
  >
> = {
  offered: { action: "accept", label: "Accept job", variant: "primary" },
  active: { action: "deactivate", label: "Deactivate", variant: "danger" },
};

export function AssignmentActions({
  assignmentId,
  status,
}: {
  assignmentId: string;
  status: Status;
}) {
  const [pending, startTransition] = useTransition();
  const [error, setError] = useState<string | undefined>();
  const step = nextStep[status];
  if (!step && status === "accepted") {
    return <p className="text-muted mt-4 text-center text-xs">Awaiting admin activation.</p>;
  }
  if (!step) return null;

  function run() {
    if (
      step!.action === "deactivate" &&
      !window.confirm("Deactivate this campaign on your vehicle? You'll stop earning from it.")
    ) {
      return;
    }
    setError(undefined);
    startTransition(async () => {
      const result = await assignmentAction({ assignmentId, action: step!.action });
      if (result.error) setError(result.error);
    });
  }

  return (
    <div className="mt-4 flex flex-col gap-2">
      <Button
        type="button"
        variant={step.variant}
        disabled={pending}
        onClick={run}
        className="h-12 w-full"
      >
        {pending ? "Working…" : step.label}
      </Button>
      {status === "offered" ? (
        <Button
          type="button"
          variant="ghost"
          disabled={pending}
          onClick={() => {
            setError(undefined);
            startTransition(async () => {
              const result = await assignmentAction({ assignmentId, action: "decline" });
              if (result.error) setError(result.error);
            });
          }}
          className="h-11 w-full"
        >
          {pending ? "Working…" : "Decline offer"}
        </Button>
      ) : null}
      {error ? (
        <p role="alert" className="text-coral text-xs">
          {error}
        </p>
      ) : null}
    </div>
  );
}
