"use client";

import { useActionState } from "react";
import { Button } from "@/components/ui/button";
import { submitCreativeForReviewAction, type CampaignReviewActionState } from "./actions";

export function CreativeStatusActions({
  campaignId,
  creativeId,
  status,
}: {
  campaignId: string;
  creativeId: string;
  status: string;
}) {
  const initialState: CampaignReviewActionState = {};
  const [state, formAction, pending] = useActionState(submitCreativeForReviewAction, initialState);

  if (status === "pending_review") {
    return <p className="micro text-amber text-right">Under admin review</p>;
  }
  if (status === "approved") {
    return <p className="micro text-green text-right">Admin approved</p>;
  }
  if (status !== "draft" && status !== "rejected") {
    return null;
  }

  return (
    <form action={formAction} className="flex flex-col items-end gap-1.5">
      <input type="hidden" name="campaign_id" value={campaignId} />
      <input type="hidden" name="creative_id" value={creativeId} />
      <Button type="submit" disabled={pending} className="h-8 px-3 text-xs">
        {pending ? "Submitting…" : status === "rejected" ? "Resubmit creative" : "Submit creative"}
      </Button>
      {state.error ? (
        <p role="alert" className="text-coral max-w-56 text-right text-xs">
          {state.error}
        </p>
      ) : null}
      {state.done && !state.error ? (
        <p className="text-green max-w-56 text-right text-xs">✓ {state.done}</p>
      ) : null}
    </form>
  );
}
