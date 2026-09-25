"use client";

import Link from "next/link";
import { useActionState } from "react";
import { Button } from "@/components/ui/button";
import type { CampaignStatus } from "@/lib/campaigns/status";
import { submitCampaignForReviewAction, type CampaignReviewActionState } from "./actions";

export function StatusActions({
  campaignId,
  status,
}: {
  campaignId: string;
  status: CampaignStatus;
}) {
  const initialState: CampaignReviewActionState = {};
  const [state, formAction, pending] = useActionState(submitCampaignForReviewAction, initialState);

  if (status === "pending_review") {
    return (
      <p className="micro text-amber max-w-xs text-right">
        Under admin review — campaign details are frozen.
      </p>
    );
  }
  if (status === "approved") {
    return (
      <p className="micro text-cyan max-w-xs text-right">
        Approved. Scheduling and activation are not available in this step.
      </p>
    );
  }
  if (status !== "draft" && status !== "rejected") {
    return null;
  }

  return (
    <form action={formAction} className="flex flex-col items-end gap-2">
      <input type="hidden" name="campaign_id" value={campaignId} />
      <div className="flex flex-wrap items-center justify-end gap-3">
        <Link
          href={`/advertiser/campaigns/${campaignId}/edit`}
          className="micro text-amber underline"
        >
          Edit details
        </Link>
        <Button type="submit" disabled={pending} className="h-10 px-4 text-xs">
          {pending
            ? "Submitting…"
            : status === "rejected"
              ? "Resubmit for review"
              : "Submit for review"}
        </Button>
      </div>
      {status === "rejected" ? (
        <p className="micro text-coral max-w-xs text-right">
          Read the reason below,{" "}
          <Link href={`/advertiser/campaigns/${campaignId}/edit`} className="underline">
            edit the details
          </Link>
          , then resubmit.
        </p>
      ) : null}
      {state.error ? (
        <p role="alert" className="text-coral text-xs">
          {state.error}
        </p>
      ) : null}
      {state.done && !state.error ? <p className="text-green text-xs">✓ {state.done}</p> : null}
    </form>
  );
}
