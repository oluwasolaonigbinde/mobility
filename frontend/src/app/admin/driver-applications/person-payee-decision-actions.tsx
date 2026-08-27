"use client";

import { useActionState } from "react";
import { Button } from "@/components/ui/button";
import { reviewPersonPayeeAction, type PersonPayeeDecisionState } from "./actions";

const initialState: PersonPayeeDecisionState = {};

export function PersonPayeeDecisionActions({
  applicationId,
  submissionId,
}: {
  applicationId: string;
  submissionId: string;
}) {
  const [state, action, pending] = useActionState(reviewPersonPayeeAction, initialState);
  return (
    <form action={action} className="flex min-w-72 flex-col gap-2">
      <input type="hidden" name="application_id" value={applicationId} />
      <input type="hidden" name="client_request_id" value={submissionId} />
      <label className="text-muted flex items-center gap-2 text-xs">
        <input type="checkbox" name="identity_match_confirmed" /> Identity matches
      </label>
      <label className="text-muted flex items-center gap-2 text-xs">
        <input type="checkbox" name="bank_account_match_confirmed" /> Account matches
      </label>
      <label className="text-muted flex items-center gap-2 text-xs">
        <input type="checkbox" name="documents_readable_confirmed" /> Documents readable
      </label>
      <label className="micro text-muted mt-1 flex flex-col gap-1">
        Rejection reason
        <select
          name="reason_code"
          defaultValue="unreadable_evidence"
          className="border-edge bg-raised text-ink rounded-lg border px-2 py-2 text-xs"
        >
          <option value="unreadable_evidence">Unreadable evidence</option>
          <option value="identity_mismatch">Identity mismatch</option>
          <option value="bank_account_mismatch">Account mismatch</option>
          <option value="unsafe_evidence">Unsafe evidence</option>
          <option value="missing_evidence">Missing evidence</option>
          <option value="rejected_evidence">Rejected evidence</option>
        </select>
      </label>
      <div className="flex flex-wrap gap-2">
        <Button
          type="submit"
          name="intent"
          value="approve"
          disabled={pending}
          className="h-8 px-2 text-xs"
        >
          Approve
        </Button>
        <Button
          type="submit"
          name="intent"
          value="reject"
          disabled={pending}
          variant="danger"
          className="h-8 px-2 text-xs"
        >
          Reject
        </Button>
        <Button
          type="submit"
          name="intent"
          value="expire"
          disabled={pending}
          variant="ghost"
          className="h-8 px-2 text-xs"
        >
          Mark expired
        </Button>
      </div>
      {state.error ? (
        <p role="alert" className="text-coral text-xs">
          {state.error}
        </p>
      ) : null}
      {state.done ? (
        <p role="status" className="text-green text-xs">
          {state.done}
        </p>
      ) : null}
    </form>
  );
}
