"use client";
import { useActionState } from "react";
import { resumeCampaign } from "./actions";
export function ResumeForm({ campaignId }: { campaignId: string }) {
  const [state, action, pending] = useActionState(
    resumeCampaign,
    {} as { error?: string; done?: string },
  );
  return (
    <details className="border-edge rounded-lg border p-3">
      <summary className="text-cyan cursor-pointer">Resume</summary>
      <form action={action} className="mt-3 grid gap-3">
        <input type="hidden" name="campaign_id" value={campaignId} />
        <label className="text-sm">
          Reason
          <textarea
            name="reason"
            required
            maxLength={1000}
            className="border-edge bg-raised mt-1 block w-full rounded border p-2"
          />
        </label>
        <button disabled={pending} className="bg-amber text-bg rounded-lg p-2">
          {pending ? "Resuming…" : "Resume campaign"}
        </button>
        {state.error ? (
          <p role="alert">{state.error}</p>
        ) : state.done ? (
          <p role="status">{state.done}</p>
        ) : null}
      </form>
    </details>
  );
}
