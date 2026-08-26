"use client";

import { useActionState, useState } from "react";
import { Button } from "@/components/ui/button";
import { Panel } from "@/components/ui/panel";
import { requestCampaignCancellationAction, type CampaignReviewActionState } from "./actions";

const initialState: CampaignReviewActionState = {};

export function CampaignCancellationPanel({
  campaignId,
  clientRequestId,
}: {
  campaignId: string;
  clientRequestId: string;
}) {
  const [confirmed, setConfirmed] = useState(false);
  const [state, formAction, pending] = useActionState(
    requestCampaignCancellationAction,
    initialState,
  );

  return (
    <Panel className="border-coral/30 mt-6 p-6" aria-label="Cancel campaign">
      <h2 className="font-display text-xl font-semibold">Cancel campaign</h2>
      <p className="text-muted mt-2 max-w-3xl text-sm">
        Cancellation is permanent. New assignments and trip starts stop at one server-recorded
        cutoff. Verified driver earnings before that cutoff remain payable. Refund eligibility is
        determined from accepted terms and production evidence; cancellation does not itself prove
        that money was transferred.
      </p>
      <form action={formAction} className="mt-5 grid gap-4">
        <input type="hidden" name="campaign_id" value={campaignId} />
        <input type="hidden" name="client_request_id" value={clientRequestId} />
        <label className="text-sm">
          <span className="micro text-muted">Reason</span>
          <textarea
            name="reason"
            required
            maxLength={1000}
            className="border-edge bg-raised mt-1 min-h-20 w-full rounded-lg border px-3.5 py-2"
            placeholder="Explain why the campaign must stop"
          />
        </label>
        <label className="flex items-start gap-3 text-sm">
          <input
            type="checkbox"
            name="confirmed"
            required
            checked={confirmed}
            onChange={(event) => setConfirmed(event.target.checked)}
            className="mt-0.5 h-4 w-4"
          />
          <span>I understand this records a permanent cancellation cutoff.</span>
        </label>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div aria-live="polite" className="text-sm">
            {state.error ? (
              <p role="alert" className="text-coral">
                {state.error}
              </p>
            ) : null}
            {state.done && !state.error ? <p className="text-green">✓ {state.done}</p> : null}
          </div>
          <Button type="submit" variant="danger" disabled={pending || !confirmed}>
            {pending ? "Cancelling…" : "Cancel campaign permanently"}
          </Button>
        </div>
      </form>
    </Panel>
  );
}
