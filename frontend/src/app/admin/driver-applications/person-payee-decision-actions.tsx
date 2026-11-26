"use client";

import { startTransition, useActionState, useEffect, useId, useState } from "react";
import { Button } from "@/components/ui/button";
import { formatDate } from "@/lib/format";
import { adminDocumentLabel } from "@/lib/status/admin";
import { ReviewDocument, SensitiveReview } from "./sensitive-review";
import {
  reviewPersonPayeeAction,
  reviewPersonPayeeEvidenceAction,
  verifyPersonPayeeAccountAction,
  type PersonPayeeDecisionState,
  type PersonPayeeEvidenceState,
} from "./actions";

const initialState: PersonPayeeDecisionState = {};
const initialEvidenceState: PersonPayeeEvidenceState = {};
const SUBMISSION_STATUS_LABELS: Record<string, string> = {
  pending_review: "Needs review",
  approved: "Approved",
  rejected: "Rejected",
  expired: "Expired",
  not_submitted: "Not submitted",
};

function EvidenceRead({
  kind,
  id,
  label,
  onRead,
}: {
  kind: "nin" | "account";
  id: string;
  label: string;
  onRead: () => void;
}) {
  const [state, action, pending] = useActionState(
    reviewPersonPayeeEvidenceAction,
    initialEvidenceState,
  );
  const idName = kind === "nin" ? "submission_id" : "bank_account_version_id";
  const revealed = Boolean(state.sensitiveValue);
  useEffect(() => {
    if (revealed) onRead();
  }, [revealed, onRead]);
  return (
    <form action={action} className="border-edge rounded-lg border p-2">
      <input type="hidden" name="kind" value={kind} />
      <input type="hidden" name={idName} value={id} />
      <Button type="submit" disabled={pending} variant="ghost" className="h-11 px-2 text-xs md:h-8">
        {pending ? "Opening…" : label}
      </Button>
      {state.sensitiveValue ? (
        <p className="mt-1 font-mono text-xs break-all" data-sensitive-review data-feedback-private>
          {state.sensitiveValue}
        </p>
      ) : null}
      {state.accountName && state.bankName ? (
        <p className="mt-1 text-xs break-words">
          <span data-feedback-private>{state.accountName}</span>
          {" · "}
          <span data-feedback-private>{state.bankName}</span>
        </p>
      ) : null}
      {state.error ? <p className="text-coral mt-1 text-xs">{state.error}</p> : null}
      {state.done ? <p className="text-green mt-1 text-xs">{state.done}</p> : null}
    </form>
  );
}

function AccountVerification({
  versionId,
  verified,
  checkedAt,
}: {
  versionId: string;
  verified: boolean;
  checkedAt?: string | null;
}) {
  const [state, action, pending] = useActionState(
    verifyPersonPayeeAccountAction,
    initialEvidenceState,
  );
  const helpId = useId();
  // Stays mounted after a successful check refreshes the page as verified,
  // so the confirmation replaces the form instead of vanishing with it.
  const verificationDate = state.verifiedAt ?? checkedAt;
  if (verified || state.done)
    return (
      <p role="status" className="text-green mt-2 text-sm">
        {verificationDate
          ? `Bank details checked on ${formatDate(verificationDate)}`
          : "Bank details checked"}
      </p>
    );
  return (
    <form action={action} className="border-edge rounded-lg border p-2">
      <input type="hidden" name="bank_account_version_id" value={versionId} />
      <label className="micro text-muted flex flex-col gap-1">
        Reference of the small test payment you sent to this account
        <input
          name="verification_reference"
          type="text"
          autoComplete="off"
          aria-describedby={helpId}
          data-feedback-private
          minLength={1}
          maxLength={512}
          required
          className="border-edge bg-raised text-ink rounded-lg border px-2 py-2 text-xs"
        />
      </label>
      <p id={helpId} className="text-muted mt-2 text-xs">
        Send a small payment to the account shown above, copy the reference from your bank&apos;s
        receipt, and check that the name your bank shows for this payment matches the driver&apos;s
        ID.
      </p>
      <Button
        type="submit"
        disabled={pending}
        variant="ghost"
        className="mt-2 h-11 px-2 text-xs md:h-8"
      >
        {pending ? "Verifying…" : "Check bank details"}
      </Button>
      {state.error ? <p className="text-coral mt-1 text-xs">{state.error}</p> : null}
    </form>
  );
}

export function PersonPayeeDecisionActions({
  applicationId,
  driverProfileId,
  submissionId,
  bankAccountVersionId,
  bankAccountVerified,
  bankCheckedAt,
  bankNameConfirmed,
  documentFileIds,
  agreementVersion,
  agreementAcceptedAt,
  status = "pending_review",
}: {
  applicationId: string;
  driverProfileId?: string;
  submissionId?: string | null;
  bankAccountVersionId?: string | null;
  bankAccountVerified: boolean;
  bankCheckedAt?: string | null;
  bankNameConfirmed?: boolean | null;
  documentFileIds: Record<string, string>;
  agreementVersion?: string | null;
  agreementAcceptedAt?: string | null;
  status?: string;
}) {
  const [state, action, pending] = useActionState(reviewPersonPayeeAction, initialState);
  const [rejectionReason, setRejectionReason] = useState("");
  const [readKeys, setReadKeys] = useState<Set<string>>(() => new Set());
  const documentNames = {
    driver_license: "Driver’s licence",
    driver_photo: "Driver photo",
  };
  const documents = [...new Set([...Object.keys(documentNames), ...Object.keys(documentFileIds)])];
  const rows = [
    { name: "Identity (NIN)", label: "Show NIN", kind: "nin" as const, id: submissionId },
    ...documents.map((key) => ({
      name: documentNames[key as keyof typeof documentNames] ?? adminDocumentLabel(key),
      label: "Open document",
      kind: "document" as const,
      id: documentFileIds[key],
    })),
    {
      name: "Bank account",
      label: "Show account number",
      kind: "account" as const,
      id: bankAccountVersionId,
    },
  ].map((row) => ({ ...row, key: JSON.stringify([row.name, row.kind, submissionId, row.id]) }));
  const checklist = rows.filter((row) => row.kind !== "document" || row.id);
  const markRead = (key: string) =>
    setReadKeys((previous) => (previous.has(key) ? previous : new Set(previous).add(key)));
  return (
    <div className="flex min-w-0 flex-col gap-2">
      {/* One submission-level status: the rows below hold different evidence, not their own decisions. */}
      <p className="text-muted mb-2 text-sm">
        Status:{" "}
        {Object.hasOwn(SUBMISSION_STATUS_LABELS, status)
          ? SUBMISSION_STATUS_LABELS[status]
          : "Status unavailable"}
        .
      </p>
      <section aria-label="Driver agreement" className="border-edge border-b py-3">
        <h3 className="font-medium">Driver agreement</h3>
        <p className="text-muted mt-1 text-sm">
          {agreementVersion && agreementAcceptedAt
            ? `Agreed to version ${agreementVersion} on ${formatDate(agreementAcceptedAt)}`
            : "Not agreed yet"}
        </p>
      </section>
      {rows.map((row) => (
        <section
          key={row.key}
          aria-label={row.name}
          className="border-edge grid gap-3 border-b py-3 sm:grid-cols-[1fr_2fr]"
        >
          <div>
            <h3 className="font-medium">{row.name}</h3>
            {row.kind === "account" && bankNameConfirmed === false ? (
              <p className="text-muted mt-1 text-sm">Name not confirmed by the bank</p>
            ) : null}
          </div>
          <div>
            {row.id ? (
              <SensitiveReview purpose="Driver application review">
                {row.kind === "document" ? (
                  (showFallback) => (
                    <ReviewDocument
                      read={() => {
                        const data = new FormData();
                        data.set("kind", "document");
                        data.set("file_id", row.id!);
                        data.set("submission_id", submissionId ?? "");
                        return reviewPersonPayeeEvidenceAction({}, data);
                      }}
                      onOpened={() => markRead(row.key)}
                      showFallback={showFallback}
                    />
                  )
                ) : (
                  <EvidenceRead
                    kind={row.kind}
                    id={row.id}
                    label={row.label}
                    onRead={() => markRead(row.key)}
                  />
                )}
              </SensitiveReview>
            ) : (
              <button type="button" disabled className="text-muted min-h-11 text-sm md:min-h-0">
                {row.label}
              </button>
            )}
            {row.kind === "account" && row.id ? (
              <AccountVerification
                versionId={row.id}
                verified={bankAccountVerified}
                checkedAt={bankCheckedAt}
              />
            ) : null}
          </div>
        </section>
      ))}
      <h3 className="mt-4 font-medium">Identity and bank decision</h3>
      {status === "pending_review" && submissionId && bankAccountVersionId ? (
        <form
          onSubmit={(event) => {
            // Submitting through onSubmit keeps the reviewer's ticks, outcomes and dates
            // after a refused decision; a form `action` would reset them.
            event.preventDefault();
            const formData = new FormData(event.currentTarget);
            const submitter = (event.nativeEvent as SubmitEvent).submitter;
            if (submitter instanceof HTMLButtonElement && submitter.name)
              formData.set(submitter.name, submitter.value);
            startTransition(() => action(formData));
          }}
          className="flex flex-col gap-2"
        >
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
              <option value="identity_mismatch">Details don&apos;t match</option>
              <option value="bank_account_mismatch">Account mismatch</option>
              <option value="unsafe_evidence">File failed safety check</option>
              <option value="missing_evidence">Missing documents</option>
              <option value="rejected_evidence">Documents not approved</option>
            </select>
          </label>
          <fieldset className="border-edge my-2 min-w-0 rounded-lg border p-3 text-xs">
            <legend>Documents that need changes</legend>
            <div className="my-3">
              <p className="font-medium">Driving licence</p>
              <label className="flex flex-col gap-1">
                Outcome
                <select
                  name="outcome_driver_license"
                  defaultValue="on_file"
                  className="border-edge bg-raised rounded border p-2"
                >
                  <option value="on_file">Not checked yet</option>
                  <option value="replace">Needs a new copy</option>
                  <option value="accepted">Looks good (view first)</option>
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
                  <option value="on_file">Not checked yet</option>
                  <option value="replace">Needs a new copy</option>
                  <option value="accepted">Looks good (view first)</option>
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
            <p>Accepted documents stay on file during renewal.</p>
          </fieldset>
          <div
            role="group"
            aria-label="Identity and bank review checklist"
            className="text-muted text-sm"
          >
            <p>
              {checklist.filter((row) => readKeys.has(row.key)).length} of {checklist.length} done
            </p>
            <ul className="flex flex-wrap gap-x-3">
              {checklist.map((row) => (
                <li key={row.key}>
                  {row.kind === "document" ? row.name : row.label}:{" "}
                  {readKeys.has(row.key) ? "Done" : "To do"}
                </li>
              ))}
            </ul>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button
              type="submit"
              name="intent"
              value="approve"
              disabled={pending}
              className="h-11 px-2 text-xs md:h-8"
            >
              Approve
            </Button>
            <Button
              type="submit"
              name="intent"
              value="reject"
              disabled={pending || !rejectionReason}
              variant="danger"
              className="h-11 px-2 text-xs md:h-8"
            >
              Reject
            </Button>
          </div>
          {state.error ? (
            <p role="alert" className="text-coral text-xs">
              {state.error}
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
      {state.done ? (
        <p role="status" className="text-green text-sm">
          {state.done}
        </p>
      ) : null}
    </div>
  );
}
