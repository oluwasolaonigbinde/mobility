"use client";

import { useRef, useState, useTransition } from "react";
import { assignmentAction } from "./actions";
import { Button } from "@/components/ui/button";
import { ConfirmationDialog } from "@/components/ui/confirmation-dialog";
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
  campaignName,
  status,
}: {
  assignmentId: string;
  campaignName: string;
  status: Status;
}) {
  const [pending, startTransition] = useTransition();
  const [error, setError] = useState<string | undefined>();
  const [confirming, setConfirming] = useState(false);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const step = nextStep[status];
  if (!step && status === "accepted") {
    return <p className="text-muted mt-4 text-center text-xs">Awaiting admin activation.</p>;
  }
  if (!step) return null;

  function run(confirmed = false) {
    if (step!.action === "deactivate" && !confirmed) {
      setConfirming(true);
      return;
    }
    setConfirming(false);
    setError(undefined);
    startTransition(async () => {
      const result = await assignmentAction({ assignmentId, action: step!.action });
      if (result.error) setError(result.error);
    });
  }

  return (
    <div className="mt-4 flex flex-col gap-2">
      <Button
        ref={triggerRef}
        type="button"
        variant={step.variant}
        disabled={pending}
        onClick={() => run()}
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
      <ConfirmationDialog
        open={confirming}
        onOpenChange={setConfirming}
        title={`Deactivate ${campaignName}?`}
        description="Tracking stops for this campaign and you will stop earning from it."
        cancelLabel="Keep campaign active"
        confirmLabel="Confirm deactivation"
        onConfirm={() => run(true)}
        returnFocusRef={triggerRef}
        pending={pending}
      />
    </div>
  );
}
