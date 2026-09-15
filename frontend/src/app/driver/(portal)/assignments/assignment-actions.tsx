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
      {confirming ? (
        <div
          role="alertdialog"
          aria-modal="true"
          aria-labelledby="deactivate-campaign-title"
          className="bg-bg/80 fixed inset-0 z-50 grid place-items-center p-4 backdrop-blur-sm"
          onKeyDown={(event) => {
            if (event.key === "Escape") setConfirming(false);
          }}
        >
          <div className="border-coral/40 bg-panel w-full max-w-sm rounded-xl border p-5 text-left shadow-xl">
            <h2 id="deactivate-campaign-title" className="font-display text-lg font-semibold">
              Deactivate {campaignName}?
            </h2>
            <p className="text-muted mt-2 text-sm">
              Tracking stops for this campaign and you will stop earning from it.
            </p>
            <div className="mt-5 flex flex-col gap-2 sm:flex-row sm:justify-end">
              <Button type="button" variant="ghost" autoFocus onClick={() => setConfirming(false)}>
                Keep campaign active
              </Button>
              <Button type="button" variant="danger" onClick={() => run(true)}>
                Confirm deactivation
              </Button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
