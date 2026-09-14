"use client";
import { useActionState } from "react";
import { resolveOperation } from "./operations-actions";
export function OperationForm({
  id,
  trip,
  contact = false,
}: {
  id: string;
  trip?: string;
  contact?: boolean;
}) {
  const [state, action, pending] = useActionState(
    resolveOperation,
    {} as { error?: string; done?: string },
  );
  return (
    <form action={action} className="mt-4 grid gap-3">
      <input type="hidden" name="id" value={id} />
      {trip ? <input type="hidden" name="trip" value={trip} /> : null}
      {contact ? (
        <>
          <input type="hidden" name="kind" value="contact" />
          <label>
            Recorded outcome
            <select name="outcome" className="border-edge bg-raised block rounded border p-2">
              <option value="attempted">Attempted</option>
              <option value="reached">Reached driver</option>
              <option value="failed">Attempt failed</option>
            </select>
          </label>
        </>
      ) : null}
      <label className="text-muted text-sm">
        {contact ? "Contact note" : "Review reason"}
        <textarea
          name="note"
          required
          maxLength={2000}
          className="border-edge bg-raised text-ink block w-full rounded border p-2"
        />
      </label>
      <label className="text-muted text-sm">
        <input type="checkbox" name="confirmed" required />{" "}
        {contact
          ? "I confirm this outcome was recorded for this task and its exact contact purpose."
          : "I reviewed this batch. This decision does not change earnings or issued reports."}
      </label>
      <div className="flex flex-wrap gap-3">
        {contact ? (
          <button disabled={pending || !!state.done} className="bg-amber text-bg rounded p-2">
            Record outcome
          </button>
        ) : (
          <>
            <button
              name="kind"
              value="apply"
              disabled={pending || !!state.done}
              className="bg-amber text-bg rounded p-2"
            >
              Apply evidence
            </button>
            <button
              name="kind"
              value="discard"
              disabled={pending || !!state.done}
              className="border-edge rounded border p-2"
            >
              Discard evidence
            </button>
          </>
        )}
      </div>
      {state.error ? (
        <p role="alert" className="text-coral">
          {state.error}
        </p>
      ) : null}
      {state.done ? (
        <p role="status" className="text-green">
          {state.done}
        </p>
      ) : null}
    </form>
  );
}
