"use client";

import { startTransition, useActionState, useState } from "react";
import { Button } from "@/components/ui/button";
import { ReviewDocument, SensitiveReview } from "./sensitive-review";
import { adminDocumentLabel } from "@/lib/status/admin";
import {
  reviewVehicleAction,
  reviewVehicleEvidenceAction,
  type VehicleDecisionState,
} from "./actions";

const initialDecisionState: VehicleDecisionState = {};
export function VehicleDecisionActions({
  applicationId,
  driverProfileId,
  vehicleId,
  submissionId,
  documentFileIds,
  status,
  defaultValidUntil,
}: {
  applicationId: string;
  driverProfileId?: string;
  vehicleId: string;
  submissionId: string;
  documentFileIds: Record<string, string>;
  status: string;
  /** Editable prefill, one calendar year ahead in Nigeria time; computed once by the server page. */
  defaultValidUntil?: string;
}) {
  const [state, action, pending] = useActionState(reviewVehicleAction, initialDecisionState);
  const [decisionRequestId] = useState(() => crypto.randomUUID());
  const [opened, setOpened] = useState<Set<string>>(() => new Set());
  const documents = Object.entries(documentFileIds).map(([name, fileId]) => ({
    key: JSON.stringify([name, vehicleId, submissionId, fileId]),
    name,
    fileId,
  }));
  const feedback = state.done ? (
    <p role="status" className="text-green text-sm">
      {state.done}
    </p>
  ) : null;
  if (status !== "approved" && status !== "pending_review") {
    return (
      <>
        {feedback}
        <p>This car needs a fresh document submission before it can be reviewed again.</p>
      </>
    );
  }
  if (status === "approved") {
    return (
      <form action={action} className="flex min-w-0 flex-col gap-2">
        <input type="hidden" name="application_id" value={applicationId} />
        {driverProfileId ? (
          <input type="hidden" name="driver_profile_id" value={driverProfileId} />
        ) : null}
        <input type="hidden" name="vehicle_id" value={vehicleId} />
        <input type="hidden" name="submission_id" value={submissionId} />
        <input type="hidden" name="client_request_id" value={decisionRequestId} />
        <p className="micro text-muted">Current approved car</p>
        <Button
          type="submit"
          name="intent"
          value="expire"
          disabled={pending}
          variant="ghost"
          className="h-11 px-2 text-xs md:h-8"
        >
          Mark expired
        </Button>
        {state.error ? (
          <p role="alert" className="text-coral text-xs">
            {state.error}
          </p>
        ) : null}
        {feedback}
      </form>
    );
  }
  return (
    <div className="flex min-w-0 flex-col gap-2">
      {documents.map(({ key, name, fileId }) => (
        <section
          key={key}
          aria-label={adminDocumentLabel(name)}
          className="border-edge border-b py-3"
        >
          <h4 className="mb-2 font-medium first-letter:uppercase">{adminDocumentLabel(name)}</h4>
          <SensitiveReview purpose="Vehicle review">
            {(showFallback) => (
              <ReviewDocument
                read={() => {
                  const data = new FormData();
                  data.set("file_id", fileId);
                  data.set("submission_id", submissionId);
                  return reviewVehicleEvidenceAction({}, data);
                }}
                onOpened={() => setOpened((previous) => new Set(previous).add(key))}
                showFallback={showFallback}
              />
            )}
          </SensitiveReview>
        </section>
      ))}
      <form
        onSubmit={(event) => {
          event.preventDefault();
          const formData = new FormData(
            event.currentTarget,
            (event.nativeEvent as SubmitEvent).submitter,
          );
          startTransition(() => action(formData));
        }}
        className="flex min-w-0 flex-col gap-2"
      >
        <input type="hidden" name="application_id" value={applicationId} />
        {driverProfileId ? (
          <input type="hidden" name="driver_profile_id" value={driverProfileId} />
        ) : null}
        <input type="hidden" name="vehicle_id" value={vehicleId} />
        <input type="hidden" name="submission_id" value={submissionId} />
        <input type="hidden" name="client_request_id" value={decisionRequestId} />
        <label className="text-muted flex items-center gap-2 text-xs">
          <input type="checkbox" name="owner_match_confirmed" /> Owner matches
        </label>
        <label className="text-muted flex items-center gap-2 text-xs">
          <input type="checkbox" name="vehicle_identity_confirmed" /> Car details match
        </label>
        <label className="text-muted flex items-center gap-2 text-xs">
          <input type="checkbox" name="roadworthy_confirmed" /> Roadworthy
        </label>
        <label className="text-muted flex items-center gap-2 text-xs">
          <input type="checkbox" name="pilot_car_confirmed" /> Meets our car requirements
        </label>
        <label className="text-muted flex items-center gap-2 text-xs">
          <input type="checkbox" name="documents_readable_confirmed" /> Documents readable
        </label>
        <label className="micro text-muted mt-1 flex flex-col gap-1">
          Car approval valid until (Nigeria time)
          <input
            name="valid_until"
            type="datetime-local"
            required
            defaultValue={state.validUntil ?? defaultValidUntil}
            className="border-edge bg-raised text-ink min-w-0 rounded-lg border px-2 py-2 text-xs"
          />
        </label>
        <label className="micro text-muted mt-1 flex flex-col gap-1">
          Rejection reason
          <select
            name="reason_code"
            defaultValue=""
            className="border-edge bg-raised text-ink min-w-0 rounded-lg border px-2 py-2 text-xs"
          >
            <option value="">Choose a reason…</option>
            <option value="unreadable_evidence">Unreadable documents</option>
            <option value="vehicle_identity_mismatch">Car details don&apos;t match</option>
            <option value="owner_mismatch">Owner mismatch</option>
            <option value="not_roadworthy">Not roadworthy</option>
            <option value="not_pilot_eligible">Doesn&apos;t meet our car requirements</option>
            <option value="unsafe_evidence">File failed safety check</option>
            <option value="missing_evidence">Missing documents</option>
          </select>
        </label>
        <fieldset className="border-edge my-2 min-w-0 rounded-lg border p-3 text-xs">
          <legend>Documents that need changes</legend>
          <div className="my-3">
            <p className="font-medium">Registration</p>
            <label className="flex flex-col gap-1">
              Outcome
              <select
                name="outcome_registration"
                defaultValue="on_file"
                className="border-edge bg-raised rounded border p-2"
              >
                <option value="on_file">Not checked yet</option>
                <option value="replace">Needs a new copy</option>
                <option value="accepted">Looks good (view first)</option>
              </select>
            </label>
            <label className="mt-2 flex flex-col gap-1">
              Registration expiry (if recorded)
              <input
                type="date"
                name="expires_registration"
                className="border-edge bg-raised rounded border p-2"
              />
            </label>
          </div>
          <div className="my-3">
            <p className="font-medium">Insurance</p>
            <label className="flex flex-col gap-1">
              Outcome
              <select
                name="outcome_insurance"
                defaultValue="on_file"
                className="border-edge bg-raised rounded border p-2"
              >
                <option value="on_file">Not checked yet</option>
                <option value="replace">Needs a new copy</option>
                <option value="accepted">Looks good (view first)</option>
              </select>
            </label>
            <label className="mt-2 flex flex-col gap-1">
              Insurance expiry (if recorded)
              <input
                type="date"
                name="expires_insurance"
                className="border-edge bg-raised rounded border p-2"
              />
            </label>
          </div>
          <div className="my-3">
            <p className="font-medium">Car photo</p>
            <label className="flex flex-col gap-1">
              Outcome
              <select
                name="outcome_vehicle_photo"
                defaultValue="on_file"
                className="border-edge bg-raised rounded border p-2"
              >
                <option value="on_file">Not checked yet</option>
                <option value="replace">Needs a new copy</option>
                <option value="accepted">Looks good (view first)</option>
              </select>
            </label>
            <label className="mt-2 flex flex-col gap-1">
              Car photo expiry (if recorded)
              <input
                type="date"
                name="expires_vehicle_photo"
                className="border-edge bg-raised rounded border p-2"
              />
            </label>
          </div>
          <p>Accepted documents stay on file during renewal.</p>
        </fieldset>
        {documents.length > 0 ? (
          <div role="group" aria-label="Opened in this visit" className="text-muted text-sm">
            <p>Opened in this visit</p>
            <ul className="flex flex-wrap gap-x-3">
              {documents.map(({ key, name }) => (
                <li key={key} className="first-letter:uppercase">
                  {adminDocumentLabel(name)}: {opened.has(key) ? "Opened" : "Not opened"}
                </li>
              ))}
            </ul>
          </div>
        ) : null}
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
            formNoValidate
            disabled={pending}
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
        {feedback}
      </form>
    </div>
  );
}
