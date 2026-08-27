"use client";

import { useActionState, useState } from "react";
import { Button } from "@/components/ui/button";
import {
  reviewVehicleAction,
  reviewVehicleEvidenceAction,
  type VehicleDecisionState,
  type VehicleEvidenceState,
} from "./actions";

const initialDecisionState: VehicleDecisionState = {};
const initialEvidenceState: VehicleEvidenceState = {};

function EvidenceRead({
  fileId,
  submissionId,
  label,
}: {
  fileId: string;
  submissionId: string;
  label: string;
}) {
  const [state, action, pending] = useActionState(
    reviewVehicleEvidenceAction,
    initialEvidenceState,
  );
  return (
    <form action={action} className="border-edge rounded-lg border p-2">
      <input type="hidden" name="file_id" value={fileId} />
      <input type="hidden" name="submission_id" value={submissionId} />
      <Button type="submit" disabled={pending} variant="ghost" className="h-8 px-2 text-xs">
        {pending ? "Opening…" : label}
      </Button>
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

export function VehicleDecisionActions({
  applicationId,
  vehicleId,
  submissionId,
  documentFileIds,
  status,
}: {
  applicationId: string;
  vehicleId: string;
  submissionId: string;
  documentFileIds: Record<string, string>;
  status: string;
}) {
  const [state, action, pending] = useActionState(reviewVehicleAction, initialDecisionState);
  const [decisionRequestId] = useState(() => crypto.randomUUID());
  if (status === "approved") {
    return (
      <form action={action} className="flex min-w-72 flex-col gap-2">
        <input type="hidden" name="application_id" value={applicationId} />
        <input type="hidden" name="vehicle_id" value={vehicleId} />
        <input type="hidden" name="submission_id" value={submissionId} />
        <input type="hidden" name="client_request_id" value={decisionRequestId} />
        <p className="micro text-muted">Current approved vehicle</p>
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
  return (
    <div className="flex min-w-72 flex-col gap-2">
      <p className="micro text-muted">Audited vehicle revision review</p>
      {Object.entries(documentFileIds).map(([name, fileId]) => (
        <EvidenceRead
          key={fileId}
          fileId={fileId}
          submissionId={submissionId}
          label={`Review ${name.replaceAll("_", " ")}`}
        />
      ))}
      <form action={action} className="flex flex-col gap-2">
        <input type="hidden" name="application_id" value={applicationId} />
        <input type="hidden" name="vehicle_id" value={vehicleId} />
        <input type="hidden" name="submission_id" value={submissionId} />
        <input type="hidden" name="client_request_id" value={decisionRequestId} />
        <label className="text-muted flex items-center gap-2 text-xs">
          <input type="checkbox" name="owner_match_confirmed" /> Owner matches
        </label>
        <label className="text-muted flex items-center gap-2 text-xs">
          <input type="checkbox" name="vehicle_identity_confirmed" /> Vehicle identity matches
        </label>
        <label className="text-muted flex items-center gap-2 text-xs">
          <input type="checkbox" name="roadworthy_confirmed" /> Roadworthy
        </label>
        <label className="text-muted flex items-center gap-2 text-xs">
          <input type="checkbox" name="pilot_car_confirmed" /> Pilot car eligible
        </label>
        <label className="text-muted flex items-center gap-2 text-xs">
          <input type="checkbox" name="documents_readable_confirmed" /> Documents readable
        </label>
        <label className="micro text-muted mt-1 flex flex-col gap-1">
          Approval expiry
          <input
            name="valid_until"
            type="datetime-local"
            className="border-edge bg-raised text-ink rounded-lg border px-2 py-2 text-xs"
          />
        </label>
        <label className="micro text-muted mt-1 flex flex-col gap-1">
          Rejection reason
          <select
            name="reason_code"
            defaultValue="unreadable_evidence"
            className="border-edge bg-raised text-ink rounded-lg border px-2 py-2 text-xs"
          >
            <option value="unreadable_evidence">Unreadable evidence</option>
            <option value="vehicle_identity_mismatch">Vehicle identity mismatch</option>
            <option value="owner_mismatch">Owner mismatch</option>
            <option value="not_roadworthy">Not roadworthy</option>
            <option value="not_pilot_eligible">Not pilot eligible</option>
            <option value="unsafe_evidence">Unsafe evidence</option>
            <option value="missing_evidence">Missing evidence</option>
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
