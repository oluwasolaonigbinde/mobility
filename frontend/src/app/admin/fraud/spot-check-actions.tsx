"use client";

import { useActionState } from "react";
import { Button } from "@/components/ui/button";
import { queueSpotCheckAction, resolveSpotCheckAction, type SpotCheckActionState } from "./actions";

const initialState: SpotCheckActionState = {};

function Result({ state }: { state: SpotCheckActionState }) {
  return (
    <div aria-live="polite">
      {state.error ? <p className="text-coral text-xs">{state.error}</p> : null}
      {state.done ? <p className="text-green text-xs">✓ {state.done}</p> : null}
    </div>
  );
}

/** Queue a physical check for a flagged trip (IDs from the flag) or, as a fallback, any trip. */
export function SpotCheckQueueForm({
  trip,
}: {
  trip?: { assignmentId: string; tripSessionId: string };
}) {
  const [state, action, pending] = useActionState(queueSpotCheckAction, initialState);
  return (
    <form action={action} className="grid gap-3 md:grid-cols-2">
      {trip ? (
        <>
          <input type="hidden" name="assignment_id" value={trip.assignmentId} />
          <input type="hidden" name="trip_session_id" value={trip.tripSessionId} />
        </>
      ) : (
        <>
          <label className="text-xs">
            <span className="text-muted mb-1 block">Assignment ID</span>
            <input
              name="assignment_id"
              required
              className="border-edge bg-bg w-full rounded-lg border px-3 py-2 font-mono"
            />
          </label>
          <label className="text-xs">
            <span className="text-muted mb-1 block">Trip ID</span>
            <input
              name="trip_session_id"
              required
              className="border-edge bg-bg w-full rounded-lg border px-3 py-2 font-mono"
            />
          </label>
        </>
      )}
      <label className="text-xs md:col-span-2">
        <span className="text-muted mb-1 block">Why this physical check is needed</span>
        <textarea
          name="note"
          required
          maxLength={2000}
          className="border-edge bg-bg min-h-20 w-full rounded-lg border px-3 py-2"
        />
      </label>
      <div className="flex items-center gap-3 md:col-span-2">
        <Button type="submit" disabled={pending} className="h-9 px-3 text-xs">
          {pending ? "Queueing…" : trip ? "Request physical check" : "Queue physical spot check"}
        </Button>
        <Result state={state} />
      </div>
    </form>
  );
}

export function SpotCheckResultForm({ verificationId }: { verificationId: string }) {
  const [state, action, pending] = useActionState(resolveSpotCheckAction, initialState);
  return (
    <form action={action} className="mt-3 flex flex-col gap-2">
      <input type="hidden" name="verification_id" value={verificationId} />
      <textarea
        name="note"
        required
        maxLength={2000}
        aria-label="Physical spot-check result note"
        placeholder="Record what staff physically observed"
        className="border-edge bg-bg min-h-20 rounded-lg border px-3 py-2 text-sm"
      />
      <div className="flex flex-wrap items-center gap-2">
        <Button
          type="submit"
          name="outcome"
          value="passed"
          disabled={pending}
          className="h-9 px-3 text-xs"
        >
          Pass
        </Button>
        <Button
          type="submit"
          name="outcome"
          value="failed"
          disabled={pending}
          variant="danger"
          className="h-9 px-3 text-xs"
        >
          Fail and hold
        </Button>
        <Result state={state} />
      </div>
    </form>
  );
}
