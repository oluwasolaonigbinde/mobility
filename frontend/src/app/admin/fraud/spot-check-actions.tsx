"use client";

import { useActionState, useRef } from "react";
import { Button } from "@/components/ui/button";
import { recordSpotCheckAction, type SpotCheckActionState } from "./actions";

const initialState: SpotCheckActionState = {};

function Result({ state }: { state: SpotCheckActionState }) {
  return (
    <div aria-live="polite">
      {state.error ? <p className="text-coral text-xs">{state.error}</p> : null}
      {state.done ? <p className="text-green text-xs">✓ {state.done}</p> : null}
    </div>
  );
}

export function SpotCheckForm({ trip }: { trip: { assignmentId: string; tripSessionId: string } }) {
  const requestId = useRef<string | null>(null);
  const [state, action, pending] = useActionState(
    async (previous: SpotCheckActionState, form: FormData) => {
      requestId.current ??= crypto.randomUUID();
      form.set("client_request_id", requestId.current);
      const result = await recordSpotCheckAction(previous, form);
      if (result.done) requestId.current = null;
      return result;
    },
    initialState,
  );
  return (
    <form action={action} className="mt-3 flex flex-col gap-2">
      <p className="text-muted text-sm">
        Staff who looked at the car record what they saw. A pass records this observation; any open
        trip review still needs its own decision. Fail opens a trip review that holds this
        trip&apos;s pay.
      </p>
      <input type="hidden" name="assignment_id" value={trip.assignmentId} />
      <input type="hidden" name="trip_session_id" value={trip.tripSessionId} />
      <textarea
        name="note"
        required
        maxLength={2000}
        aria-label="In-person check result note"
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
