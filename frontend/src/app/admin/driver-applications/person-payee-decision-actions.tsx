"use client";

import { useActionState } from "react";
import { Button } from "@/components/ui/button";
import { SensitiveReview } from "./sensitive-review";
import { adminDocumentLabel } from "@/lib/status/admin";
import {
  reviewPersonPayeeAction,
  reviewPersonPayeeEvidenceAction,
  verifyPersonPayeeAccountAction,
  type PersonPayeeDecisionState,
  type PersonPayeeEvidenceState,
} from "./actions";

const initialState: PersonPayeeDecisionState = {};
const initialEvidenceState: PersonPayeeEvidenceState = {};

function EvidenceRead({
  kind,
  id,
  label,
  submissionId,
}: {
  kind: "nin" | "account" | "document";
  id: string;
  label: string;
  submissionId?: string;
}) {
  const [state, action, pending] = useActionState(
    reviewPersonPayeeEvidenceAction,
    initialEvidenceState,
  );
  const idName =
    kind === "nin" ? "submission_id" : kind === "account" ? "bank_account_version_id" : "file_id";
  return (
    <form action={action} className="border-edge rounded-lg border p-2">
      <input type="hidden" name="kind" value={kind} />
      <input type="hidden" name={idName} value={id} />
      {submissionId ? <input type="hidden" name="submission_id" value={submissionId} /> : null}
      <Button type="submit" disabled={pending} variant="ghost" className="h-8 px-2 text-xs">
        {pending ? "Opening…" : label}
      </Button>
      {state.sensitiveValue ? (
        <p className="mt-1 font-mono text-xs break-all" data-sensitive-review>
          {state.sensitiveValue}
        </p>
      ) : null}
      {state.downloadUrl ? (
        <a
          href={state.downloadUrl}
          target="_blank"
          rel="noreferrer"
          className="text-cyan mt-1 block text-xs underline"
        >
          Open reviewed document
        </a>
      ) : null}
      {state.error ? <p className="text-coral mt-1 text-xs">{state.error}</p> : null}
      {state.done ? <p className="text-green mt-1 text-xs">{state.done}</p> : null}
    </form>
  );
}

function AccountVerification({ versionId }: { versionId: string }) {
  const [state, action, pending] = useActionState(
    verifyPersonPayeeAccountAction,
    initialEvidenceState,
  );
  return (
    <form action={action} className="border-edge rounded-lg border p-2">
      <input type="hidden" name="bank_account_version_id" value={versionId} />
      <label className="micro text-muted flex flex-col gap-1">
        Approved bank check reference
        <input
          name="verification_reference"
          type="password"
          minLength={16}
          maxLength={512}
          required
          className="border-edge bg-raised text-ink rounded-lg border px-2 py-2 text-xs"
        />
      </label>
      <Button type="submit" disabled={pending} variant="ghost" className="mt-2 h-8 px-2 text-xs">
        {pending ? "Verifying…" : "Check bank details"}
      </Button>
      {state.error ? <p className="text-coral mt-1 text-xs">{state.error}</p> : null}
      {state.done ? <p className="text-green mt-1 text-xs">{state.done}</p> : null}
    </form>
  );
}

export function PersonPayeeDecisionActions({
  applicationId,
  submissionId,
  bankAccountVersionId,
  bankAccountVerified,
  documentFileIds,
  status = "pending_review",
}: {
  applicationId: string;
  submissionId: string;
  bankAccountVersionId: string;
  bankAccountVerified: boolean;
  documentFileIds: Record<string, string>;
  status?: string;
}) {
  const [state, action, pending] = useActionState(reviewPersonPayeeAction, initialState);
  return (
    <div className="flex min-w-0 flex-col gap-2">
      <p className="micro text-muted">Review the current documents and bank details (logged)</p>
      <SensitiveReview purpose="Identity documents and bank details">
        <EvidenceRead kind="nin" id={submissionId} label="Show NIN (logged)" />
      </SensitiveReview>
      <SensitiveReview purpose="Identity documents and bank details">
        <EvidenceRead kind="account" id={bankAccountVersionId} label="Show bank details (logged)" />
      </SensitiveReview>
      {Object.entries(documentFileIds).map(([name, fileId]) => (
        <SensitiveReview key={fileId} purpose="Identity documents and bank details">
          <EvidenceRead
            key={fileId}
            kind="document"
            id={fileId}
            submissionId={submissionId}
            label={`Review ${adminDocumentLabel(name)}`}
          />
        </SensitiveReview>
      ))}
      {bankAccountVerified ? (
        <p className="text-green text-xs">These bank details have been checked for payouts.</p>
      ) : (
        <AccountVerification versionId={bankAccountVersionId} />
      )}
      {status === "pending_review" ? (
        <form action={action} className="flex flex-col gap-2">
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
              <option value="unreadable_evidence">Unreadable documents</option>
              <option value="identity_mismatch">Identity mismatch</option>
              <option value="bank_account_mismatch">Account mismatch</option>
              <option value="unsafe_evidence">Unsafe documents</option>
              <option value="missing_evidence">Missing documents</option>
              <option value="rejected_evidence">Documents not approved</option>
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
      ) : (
        <p className="text-muted text-sm">
          Current identity decision: {status === "approved" ? "Approved" : "Not approved"}.
        </p>
      )}
    </div>
  );
}
