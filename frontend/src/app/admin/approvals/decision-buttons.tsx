"use client";

import { useFormStatus } from "react-dom";
import { Button } from "@/components/ui/button";

/**
 * Approve/reject submit pair for a review form. The pending label follows the
 * button that submitted the form, so a running rejection never reads as an
 * approval. Must be rendered inside the decision `<form>`.
 */
export function DecisionButtons({
  approveLabel = "Approve",
  rejectLabel = "Reject",
}: {
  approveLabel?: string;
  rejectLabel?: string;
}) {
  const { pending, data } = useFormStatus();
  const intent = pending ? data?.get("intent") : null;

  return (
    <div className="flex gap-2">
      <Button
        type="submit"
        name="intent"
        value="approve"
        disabled={pending}
        className="h-9 px-3 text-xs"
      >
        {intent === "approve" ? "Approving…" : approveLabel}
      </Button>
      <Button
        type="submit"
        name="intent"
        value="reject"
        variant="danger"
        disabled={pending}
        className="h-9 px-3 text-xs"
      >
        {intent === "reject" ? "Rejecting…" : rejectLabel}
      </Button>
    </div>
  );
}
