"use client";
import { useRef, useState, useTransition, type FormEvent } from "react";
import { ConfirmationDialog } from "@/components/ui/confirmation-dialog";
import { cancelWholeCampaign, type StaffCancellationState } from "./cancellation-actions";

export function CancelCampaignForm({
  campaignId,
  campaignName,
  complaintId,
}: {
  campaignId: string;
  campaignName: string;
  complaintId?: string;
}) {
  const [reason, setReason] = useState("");
  const [confirming, setConfirming] = useState(false);
  const [state, setState] = useState<StaffCancellationState>({});
  const [pending, start] = useTransition();
  const request = useRef<string | null>(null);
  const sending = useRef(false);
  const trigger = useRef<HTMLButtonElement>(null);
  function review(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!reason.trim() || reason.trim().length > 1000) {
      setState({ error: "Add a reason using 1–1,000 characters." });
      return;
    }
    setConfirming(true);
  }
  function confirm() {
    if (sending.current || !reason.trim()) return;
    sending.current = true;
    request.current ??= crypto.randomUUID();
    start(async () => {
      try {
        const result = await cancelWholeCampaign({
          campaignId,
          complaintId,
          reason: reason.trim(),
          requestId: request.current!,
        });
        setState(result);
        if (result.done) setConfirming(false);
      } catch {
        setState({
          error:
            "Cancellation couldn’t be confirmed. Retry with the same reason to check this request.",
        });
      } finally {
        sending.current = false;
      }
    });
  }
  if (state.done)
    return (
      <p role="status" className="text-green mt-4 text-sm">
        {state.done}
      </p>
    );
  return (
    <section aria-label="Cancel campaign" className="border-edge mt-5 border-t pt-4">
      <h3 className="font-medium">Cancel campaign</h3>
      <form onSubmit={review} className="mt-3 grid gap-3">
        <label className="text-sm">
          Reason
          <textarea
            name="reason"
            required
            minLength={1}
            maxLength={1000}
            disabled={pending}
            value={reason}
            onChange={(event) => {
              setReason(event.target.value);
              request.current = null;
              setState({});
            }}
            className="border-edge bg-raised mt-2 min-h-24 w-full rounded border p-3"
          />
        </label>
        <button
          ref={trigger}
          disabled={pending}
          type="submit"
          className="text-coral justify-self-start rounded border px-4 py-2 text-sm"
        >
          Cancel campaign
        </button>
        {!confirming && state.error ? <p role="alert">{state.error}</p> : null}
      </form>
      <ConfirmationDialog
        open={confirming}
        onOpenChange={setConfirming}
        title={`Cancel ${campaignName}?`}
        description="This stops new campaign work. Drivers are paid for valid work already done. Terrax Media will review any settlement; this does not confirm a refund."
        cancelLabel="Keep campaign running"
        confirmLabel="Cancel campaign"
        returnFocusRef={trigger}
        pending={pending}
        error={state.error}
        onConfirm={confirm}
      >
        <p className="text-sm">{reason.trim()}</p>
      </ConfirmationDialog>
    </section>
  );
}
