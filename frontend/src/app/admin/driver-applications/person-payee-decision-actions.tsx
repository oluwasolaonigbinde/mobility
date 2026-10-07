"use client";

import { useActionState, useState } from "react";
import { Button } from "@/components/ui/button";
import { SensitiveReview } from "./sensitive-review";
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
        Bank check reference, from the bank confirmation
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
  driverProfileId,
  submissionId,
  bankAccountVersionId,
  bankAccountVerified,
  documentFileIds,
  status = "pending_review",
}: {
  applicationId: string;
  driverProfileId?: string;
  submissionId?: string | null;
  bankAccountVersionId?: string | null;
  bankAccountVerified: boolean;
  documentFileIds: Record<string, string>;
  status?: string;
}) {
  const [state, action, pending] = useActionState(reviewPersonPayeeAction, initialState);
  const [rejectionReason, setRejectionReason] = useState("");
  return (
    <div className="flex min-w-0 flex-col gap-2">
      <p className="text-muted mb-2 text-sm">
        Each view is logged. Documents are hidden after one minute or when you leave this page.
      </p>
      <p className="text-faint mb-2 text-xs">
        Identity documents are reviewed together. Bank details are checked separately before the
        combined decision.
      </p>
      {[
        { name: "Identity (NIN)", kind: "nin" as const, id: submissionId },
        { name: "Driver’s licence", kind: "document" as const, id: documentFileIds.driver_license },
        { name: "Driver photo", kind: "document" as const, id: documentFileIds.driver_photo },
        {
          name: "Signed agreement",
          kind: "document" as const,
          id: documentFileIds.signed_agreement,
        },
        { name: "Bank account", kind: "account" as const, id: bankAccountVersionId },
      ].map((row) => (
        <section
          key={`${row.name}:${submissionId ?? "missing"}:${row.id ?? "missing"}`}
          aria-label={row.name}
          className="border-edge grid gap-3 border-b py-3 sm:grid-cols-[1fr_2fr]"
        >
          <div>
            <h3 className="font-medium">{row.name}</h3>
            <p className="text-muted mt-1 text-sm">
              {!row.id
                ? "Not submitted"
                : ({
                    pending_review: "Needs review",
                    approved: "Approved",
                    rejected: "Rejected",
                    expired: "Expired",
                  }[status] ?? "Status unavailable")}
            </p>
            {row.kind === "account" && bankAccountVerified ? (
              <p className="text-green mt-1 text-xs">Bank details checked</p>
            ) : null}
          </div>
          <div>
            {row.id ? (
              <SensitiveReview purpose="Driver application review">
                <EvidenceRead
                  kind={row.kind}
                  id={row.id}
                  submissionId={row.kind === "document" ? (submissionId ?? undefined) : undefined}
                  label={row.kind === "nin" ? "Show NIN" : "View"}
                />
              </SensitiveReview>
            ) : (
              <button type="button" disabled className="text-muted text-sm">
                {row.kind === "nin" ? "Show NIN" : "View"}
              </button>
            )}
            {row.kind === "account" && row.id && !bankAccountVerified ? (
              <AccountVerification versionId={row.id} />
            ) : null}
          </div>
        </section>
      ))}
      <h3 className="mt-4 font-medium">Identity and bank decision</h3>
      {status === "pending_review" && submissionId && bankAccountVersionId ? (
        <form action={action} className="flex flex-col gap-2">
          <input type="hidden" name="application_id" value={applicationId} />
          {driverProfileId ? (
            <input type="hidden" name="driver_profile_id" value={driverProfileId} />
          ) : null}
          <input type="hidden" name="client_request_id" value={submissionId} />
          <input type="hidden" name="submission_id" value={submissionId} />
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
              value={rejectionReason}
              onChange={(event) => setRejectionReason(event.target.value)}
              className="border-edge bg-raised text-ink rounded-lg border px-2 py-2 text-xs"
            >
              <option value="">Choose a reason…</option>
              <option value="unreadable_evidence">Unreadable documents</option>
              <option value="identity_mismatch">Identity mismatch</option>
              <option value="bank_account_mismatch">Account mismatch</option>
              <option value="unsafe_evidence">Unsafe documents</option>
              <option value="missing_evidence">Missing documents</option>
              <option value="rejected_evidence">Documents not approved</option>
            </select>
          </label>
          <fieldset className="border-edge my-2 rounded-lg border p-3 text-xs">
            <legend>Document outcomes for rejection or expiry</legend>
            <div className="my-3">
              <p className="font-medium">Driving licence</p>
              <label className="flex flex-col gap-1">
                Outcome
                <select
                  name="outcome_driver_license"
                  defaultValue="on_file"
                  className="border-edge bg-raised rounded border p-2"
                >
                  <option value="on_file">On file, review incomplete</option>
                  <option value="replace">Needs replacement</option>
                  <option value="accepted">Accepted (view first)</option>
                </select>
              </label>
              <label className="mt-2 flex flex-col gap-1">
                Driving licence expiry (if recorded)
                <input
                  type="date"
                  name="expires_driver_license"
                  className="border-edge bg-raised rounded border p-2"
                />
              </label>
            </div>
            <div className="my-3">
              <p className="font-medium">Driver photo</p>
              <label className="flex flex-col gap-1">
                Outcome
                <select
                  name="outcome_driver_photo"
                  defaultValue="on_file"
                  className="border-edge bg-raised rounded border p-2"
                >
                  <option value="on_file">On file, review incomplete</option>
                  <option value="replace">Needs replacement</option>
                  <option value="accepted">Accepted (view first)</option>
                </select>
              </label>
              <label className="mt-2 flex flex-col gap-1">
                Driver photo expiry (if recorded)
                <input
                  type="date"
                  name="expires_driver_photo"
                  className="border-edge bg-raised rounded border p-2"
                />
              </label>
            </div>
            <div className="my-3">
              <p className="font-medium">Signed agreement</p>
              <label className="flex flex-col gap-1">
                Outcome
                <select
                  name="outcome_signed_agreement"
                  defaultValue="on_file"
                  className="border-edge bg-raised rounded border p-2"
                >
                  <option value="on_file">On file, review incomplete</option>
                  <option value="replace">Needs replacement</option>
                  <option value="accepted">Accepted (view first)</option>
                </select>
              </label>
              <label className="mt-2 flex flex-col gap-1">
                Signed agreement expiry (if recorded)
                <input
                  type="date"
                  name="expires_signed_agreement"
                  className="border-edge bg-raised rounded border p-2"
                />
              </label>
            </div>
            <p>Record each document’s outcome. Accepted documents stay on file during renewal.</p>
          </fieldset>
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
              disabled={pending || !rejectionReason}
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
          Current identity decision:{" "}
          {{
            approved: "Approved",
            rejected: "Rejected",
            expired: "Expired",
            not_submitted: "Not submitted",
          }[status] ?? "Unavailable"}
          .
        </p>
      )}
    </div>
  );
}
