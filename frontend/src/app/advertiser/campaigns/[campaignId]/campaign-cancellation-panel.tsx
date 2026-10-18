"use client";
import { useState } from "react";

/** Agreed Worker A contract. Submission is connected in Phase 2. */
export interface CampaignCancellationRequest {
  category: "campaign_cancellation";
  reference_type: "campaign";
  reference_id: string;
  message: string;
  client_request_id: string;
}

export function CampaignCancellationPanel({
  campaignId,
  campaignName,
}: {
  campaignId: string;
  campaignName: string;
}) {
  const [reason, setReason] = useState("");
  const [touched, setTouched] = useState(false);
  const reasonError = touched && !reason.trim() ? "Please add a short reason." : undefined;
  const subject = encodeURIComponent(`Cancellation request: ${campaignName}`);
  return (
    <section aria-label="Ask Terrax to cancel" className="border-edge mt-6 border-t pt-6">
      <h2 className="font-display text-xl font-semibold">Ask Terrax to cancel this campaign</h2>
      <label className="mt-4 grid gap-2 text-sm">
        <span>Why would you like to cancel?</span>
        <textarea
          value={reason}
          onChange={(event) => setReason(event.target.value)}
          onBlur={() => setTouched(true)}
          name="reason"
          required
          minLength={1}
          maxLength={2000}
          aria-invalid={Boolean(reasonError)}
          aria-describedby={reasonError ? "cancel-reason-error" : undefined}
          className="border-edge min-h-24 w-full rounded-xl border bg-white p-3"
        />
      </label>
      {reasonError ? (
        <p id="cancel-reason-error" role="alert" className="text-coral mt-2 text-sm">
          {reasonError}
        </p>
      ) : null}
      <button type="button" disabled className="brand-action mt-4" data-campaign-id={campaignId}>
        Ask Terrax to cancel
      </button>
      <p className="text-muted mt-3 text-sm">
        Contact Terrax Media to arrange cancellation.{" "}
        <a
          className="text-green underline"
          href={`mailto:terraxmediacompany@gmail.com?subject=${subject}&body=${encodeURIComponent(reason.trim())}`}
        >
          Email Terrax Media
        </a>
      </p>
    </section>
  );
}
