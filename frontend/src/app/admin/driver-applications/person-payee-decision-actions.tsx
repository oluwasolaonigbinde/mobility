"use client";

import { useActionState } from "react";
import { Button } from "@/components/ui/button";
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
        Authorized verification reference
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
        {pending ? "Verifying…" : "Verify exact account version"}
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
}: {
  applicationId: string;
  submissionId: string;
  bankAccountVersionId: string;
  bankAccountVerified: boolean;
  documentFileIds: Record<string, string>;
}) {
  const [state, action, pending] = useActionState(reviewPersonPayeeAction, initialState);
  return (
    <div className="flex min-w-72 flex-col gap-2">
      <p className="micro text-muted">Audited exact-version review</p>
      <EvidenceRead kind="nin" id={submissionId} label="Reveal NIN" />
      <EvidenceRead kind="account" id={bankAccountVersionId} label="Reveal account" />
      {Object.entries(documentFileIds).map(([name, fileId]) => (
        <EvidenceRead
          key={fileId}
          kind="document"
          id={fileId}
          submissionId={submissionId}
          label={`Review ${name.replaceAll("_", " ")}`}
        />
      ))}
      {bankAccountVerified ? (
        <p className="text-green text-xs">Exact account version is payout-verified.</p>
      ) : (
        <AccountVerification versionId={bankAccountVersionId} />
      )}
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
    </div>
  );
}
