"use client";

import { useActionState } from "react";
import { processTripAction, type ProcessTripState } from "./actions";
import { Button } from "@/components/ui/button";

const initialState: ProcessTripState = {};

export function ProcessTripForm() {
  const [state, formAction, pending] = useActionState(processTripAction, initialState);

  return (
    <form action={formAction} className="flex flex-col gap-3">
      <label htmlFor="pt-trip" className="micro text-muted">
        Trip ID
      </label>
      <div className="flex gap-2">
        <input
          id="pt-trip"
          name="trip_id"
          required
          placeholder="paste a trip UUID"
          className="border-edge bg-raised text-ink placeholder:text-faint focus:border-amber h-11 flex-1 rounded-lg border px-3.5 font-mono text-xs focus:outline-none"
        />
        <Button type="submit" disabled={pending} className="shrink-0">
          {pending ? "Processing…" : "Run pipeline"}
        </Button>
      </div>

      {state.error ? (
        <p
          role="alert"
          className="border-coral/40 bg-coral/10 text-coral rounded-lg border px-3.5 py-2.5 text-sm"
        >
          {state.error}
        </p>
      ) : null}
      {!state.error && state.steps?.length ? (
        <ol className="border-green/40 bg-green/10 flex flex-col gap-1.5 rounded-lg border px-3.5 py-2.5">
          {state.steps.map((s, i) => (
            <li key={i} className="text-green text-xs">
              ✓ {s}
            </li>
          ))}
        </ol>
      ) : null}
    </form>
  );
}
