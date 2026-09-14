"use client";
import { useActionState, useState } from "react";
import { issueMeasurement } from "./actions";
import { SearchSelect } from "../search-select";
export function IssueMeasurementForm() {
  const [request] = useState(() => crypto.randomUUID());
  const [state, action, pending] = useActionState(
    issueMeasurement,
    {} as { error?: string; done?: string },
  );
  return (
    <details className="border-edge mb-6 rounded-xl border p-4">
      <summary className="cursor-pointer">Prepare a measurement run</summary>
      <form action={action} className="mt-4 grid gap-3">
        <input type="hidden" name="client_request_id" value={request} />
        <SearchSelect kind="campaign" name="campaign_id" label="Campaign" />
        <label>
          Period start (UTC)
          <input
            name="period_start_at"
            placeholder="2026-09-01T00:00:00Z"
            required
            className="border-edge bg-raised block w-full rounded border p-2"
          />
        </label>
        <label>
          Period end (UTC, excluded)
          <input
            name="period_end_at"
            placeholder="2026-10-01T00:00:00Z"
            required
            className="border-edge bg-raised block w-full rounded border p-2"
          />
        </label>
        <label>
          <input type="checkbox" name="test_only" /> Synthetic test data only
        </label>
        <p className="text-muted text-sm">
          Creates an immutable measurement snapshot using the existing reporting method. It does not
          issue downloads, confirm physical activity, or calculate ROI. Live method and privacy
          approval remain required.
        </p>
        <button disabled={pending} className="bg-amber text-bg rounded p-3">
          {pending ? "Preparing…" : "Prepare measurement run"}
        </button>
        {state.error ? <p role="alert">{state.error}</p> : null}
        {state.done ? <p role="status">{state.done}</p> : null}
      </form>
    </details>
  );
}
