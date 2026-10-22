"use client";
import { useActionState } from "react";
import { resolveOperation } from "./operations-actions";
export function OperationForm({ id }: { id: string }) {
  const [state, action, pending] = useActionState(
    resolveOperation,
    {} as { error?: string; done?: string },
  );
  return (
    <form action={action} className="mt-4 grid gap-3">
      <input type="hidden" name="id" value={id} />
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
      <label className="text-muted text-sm">
        Contact note
        <textarea
          name="note"
          required
          maxLength={2000}
          className="border-edge bg-raised text-ink block w-full rounded border p-2"
        />
      </label>
      <label className="text-muted text-sm">
        <input type="checkbox" name="confirmed" required /> I confirm this outcome was recorded for
        this task and its exact contact purpose.
      </label>
      <div className="flex flex-wrap gap-3">
        <button disabled={pending || !!state.done} className="bg-amber text-bg rounded p-2">
          Record outcome
        </button>
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
