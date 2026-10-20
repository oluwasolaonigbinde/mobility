"use client";
import { useRef, useState, useTransition, type FormEvent } from "react";
import Link from "next/link";
import {
  requestCampaignCancellation,
  type CancellationRequestState,
} from "./cancellation-request-actions";

export function CampaignCancellationPanel({
  campaignId,
  campaignName,
  pendingThreadId,
}: {
  campaignId: string;
  campaignName: string;
  /** An open or answered cancellation request already sent for this campaign (REQ-194). */
  pendingThreadId?: string;
}) {
  const [reason, setReason] = useState("");
  const [touched, setTouched] = useState(false);
  const [state, setState] = useState<CancellationRequestState>(
    pendingThreadId ? { threadId: pendingThreadId } : {},
  );
  // Sent from this panel, not found on load; the refreshed page then passes the same thread as pending.
  const [sent, setSent] = useState(false);
  const [pending, start] = useTransition();
  const request = useRef<string | null>(null);
  const sending = useRef(false);
  const reasonError = touched && !reason.trim() ? "Please add a short reason." : undefined;
  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setTouched(true);
    if (!reason.trim() || reason.trim().length > 2000 || sending.current) return;
    request.current ??= crypto.randomUUID();
    sending.current = true;
    start(async () => {
      try {
        const result = await requestCampaignCancellation(
          campaignId,
          reason.trim(),
          request.current!,
        );
        setSent(Boolean(result.threadId));
        setState(result);
      } catch {
        setState({
          error: "We couldn’t confirm your request. Try sending the same request again.",
        });
      } finally {
        sending.current = false;
      }
    });
  }
  if (state.threadId)
    return (
      <section aria-label="Cancellation request" className="mt-6" role="status">
        <p className="text-ink text-base">
          {sent ? "Request sent." : "Cancellation requested."} Your campaign continues until Terrax
          confirms.
        </p>
        <Link
          className="text-green mt-3 inline-block underline"
          href={`/advertiser/help/${state.threadId}`}
        >
          View cancellation request
        </Link>
      </section>
    );
  return (
    <section aria-label="Ask Terrax to cancel" className="border-edge mt-6 border-t pt-6">
      <h2 className="font-display text-xl font-semibold">Ask Terrax to cancel this campaign</h2>
      <p className="text-muted mt-3 text-sm">
        Tell Terrax Media why you’d like to stop {campaignName}.
      </p>
      <form onSubmit={submit}>
        <label className="mt-4 grid gap-2 text-sm">
          <span>Why would you like to cancel?</span>
          <textarea
            value={reason}
            onChange={(event) => {
              setReason(event.target.value);
              request.current = null;
              setState({});
            }}
            onBlur={() => setTouched(true)}
            name="reason"
            required
            disabled={pending}
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
        {state.error ? (
          <p role="alert" className="text-coral mt-2 text-sm">
            {state.error}
          </p>
        ) : null}
        <button type="submit" disabled={pending} className="brand-action mt-4">
          {pending ? "Sending…" : "Ask Terrax to cancel"}
        </button>
      </form>
    </section>
  );
}
