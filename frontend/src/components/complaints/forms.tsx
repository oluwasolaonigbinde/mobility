"use client";

import { useActionState, useId, useRef } from "react";
import { Button } from "@/components/ui/button";
import type { ComplaintActionState } from "@/lib/complaints/actions";
import { CATEGORY_LABELS, PARTY_CATEGORIES, type ComplaintParty } from "@/lib/complaints/labels";

type Action = (state: ComplaintActionState, formData: FormData) => Promise<ComplaintActionState>;

export interface ReferenceOption {
  id: string;
  label: string;
}

export interface ReferenceGroups {
  campaigns: ReferenceOption[];
  trips: ReferenceOption[];
  payouts: ReferenceOption[];
}

const initial: ComplaintActionState = {};

/**
 * One idempotency key per message: kept across retries of the same send and
 * renewed only after a success. It is assigned at submit time rather than
 * rendered, so server and client HTML always match.
 */
function useIdempotentAction(action: Action) {
  const requestId = useRef<string | null>(null);
  return useActionState(async (previous: ComplaintActionState, formData: FormData) => {
    requestId.current ??= crypto.randomUUID();
    formData.set("client_request_id", requestId.current);
    const next = await action(previous, formData);
    if (next.done) requestId.current = null;
    return next;
  }, initial);
}

const inputClass =
  "border-edge bg-raised text-ink focus:border-amber w-full rounded-lg border px-3 py-2 text-sm focus:outline-none";

function Feedback({ state }: { state: ComplaintActionState }) {
  return (
    <div aria-live="polite">
      {state.error ? (
        <p role="alert" className="text-coral text-sm">
          {state.error}
        </p>
      ) : null}
      {state.done && !state.error ? <p className="text-green text-sm">✓ {state.done}</p> : null}
    </div>
  );
}

function MessageField({ label, placeholder }: { label: string; placeholder: string }) {
  const id = useId();
  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={id} className="micro text-muted">
        {label}
      </label>
      <textarea
        id={id}
        name="message"
        required
        maxLength={2000}
        placeholder={placeholder}
        className={`${inputClass} min-h-28`}
      />
    </div>
  );
}

/** Raise a complaint: category, optional own record, message. */
export function RaiseComplaintForm({
  party,
  action,
  references,
}: {
  party: ComplaintParty;
  action: Action;
  references: ReferenceGroups | null;
}) {
  const [state, formAction, pending] = useIdempotentAction(action);
  const categoryId = useId();
  const referenceId = useId();
  const groups: Array<[string, "campaign" | "trip" | "payout", ReferenceOption[]]> = references
    ? [
        [party === "driver" ? "Jobs" : "Campaigns", "campaign", references.campaigns],
        ["Trips", "trip", references.trips],
        ["Payouts", "payout", references.payouts],
      ]
    : [];

  return (
    <form action={formAction} className="flex flex-col gap-4">
      <div className="flex flex-col gap-1.5">
        <label htmlFor={categoryId} className="micro text-muted">
          What is it about?
        </label>
        <select id={categoryId} name="category" required defaultValue="" className={inputClass}>
          <option value="" disabled>
            Choose one
          </option>
          {PARTY_CATEGORIES[party].map((category) => (
            <option key={category} value={category}>
              {CATEGORY_LABELS[category]}
            </option>
          ))}
        </select>
      </div>
      <div className="flex flex-col gap-1.5">
        <label htmlFor={referenceId} className="micro text-muted">
          Which {party === "driver" ? "job, trip or payout" : "campaign"}? (optional)
        </label>
        <select id={referenceId} name="reference" defaultValue="" className={inputClass}>
          <option value="">None — it&apos;s about something else</option>
          {groups
            .filter(([, , options]) => options.length > 0)
            .map(([label, type, options]) => (
              <optgroup key={type} label={label}>
                {options.map((option) => (
                  <option key={option.id} value={`${type}:${option.id}`}>
                    {option.label}
                  </option>
                ))}
              </optgroup>
            ))}
        </select>
        {references === null ? (
          <p className="text-muted text-xs">
            Your {party === "driver" ? "jobs, trips and payouts" : "campaigns"} couldn&apos;t be
            loaded, so you can&apos;t pick one right now. You can still describe it in your message.
          </p>
        ) : null}
      </div>
      <MessageField
        label="Tell us what happened"
        placeholder="Say what went wrong and what you would like Terrax Media to do."
      />
      <Button type="submit" disabled={pending} className="self-start">
        {pending ? "Sending…" : "Send complaint"}
      </Button>
      <Feedback state={state} />
    </form>
  );
}

/** Add a message to an existing complaint (complainant or staff reply). */
export function ComplaintMessageForm({
  complaintId,
  action,
  label,
  placeholder,
  submitLabel,
  allowResolve = false,
}: {
  complaintId: string;
  action: Action;
  label: string;
  placeholder: string;
  submitLabel: string;
  allowResolve?: boolean;
}) {
  // The form stays mounted when the new message arrives, so the confirmation
  // remains visible; React clears the fields after the action.
  const [state, formAction, pending] = useIdempotentAction(action);
  return (
    <form action={formAction} className="flex flex-col gap-3">
      <input type="hidden" name="complaint_id" value={complaintId} />
      <MessageField label={label} placeholder={placeholder} />
      {allowResolve ? (
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" name="resolve" /> Mark as resolved with this reply
        </label>
      ) : null}
      <Button type="submit" disabled={pending} className="self-start">
        {pending ? "Sending…" : submitLabel}
      </Button>
      <Feedback state={state} />
    </form>
  );
}

/** Staff status and assignment. */
export function ComplaintUpdateForm({
  complaintId,
  action,
  staff,
}: {
  complaintId: string;
  action: Action;
  staff: ReferenceOption[] | null;
}) {
  const [state, formAction, pending] = useActionState(action, initial);
  const statusId = useId();
  const assigneeId = useId();
  return (
    <form action={formAction} className="flex flex-col gap-3">
      <input type="hidden" name="complaint_id" value={complaintId} />
      <div className="flex flex-col gap-1.5">
        <label htmlFor={statusId} className="micro text-muted">
          Status
        </label>
        <select id={statusId} name="status" defaultValue="" className={inputClass}>
          <option value="">Keep as it is</option>
          <option value="open">Reopen (needs a reply)</option>
          <option value="resolved">Mark as resolved</option>
        </select>
      </div>
      <div className="flex flex-col gap-1.5">
        <label htmlFor={assigneeId} className="micro text-muted">
          Assigned to
        </label>
        <select
          id={assigneeId}
          name="assignee"
          defaultValue=""
          disabled={staff === null}
          className={inputClass}
        >
          <option value="">Keep as it is</option>
          <option value="none">Nobody</option>
          {(staff ?? []).map((person) => (
            <option key={person.id} value={person.id}>
              {person.label}
            </option>
          ))}
        </select>
        {staff === null ? (
          <p className="text-muted text-xs">The staff list couldn&apos;t be loaded.</p>
        ) : null}
      </div>
      <Button type="submit" disabled={pending} className="self-start">
        {pending ? "Saving…" : "Save"}
      </Button>
      <Feedback state={state} />
    </form>
  );
}
