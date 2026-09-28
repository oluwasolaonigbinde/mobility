"use client";

import { useActionState } from "react";
import { Button } from "@/components/ui/button";
import {
  releaseUnsentAction,
  resolveAlertAction,
  switchAutomaticPayoutsAction,
  type AutomaticActionState,
} from "./actions";

const initial: AutomaticActionState = {};

function Feedback({ state }: { state: AutomaticActionState }) {
  if (state.error) {
    return (
      <p role="alert" className="text-coral text-sm">
        {state.error}
      </p>
    );
  }
  if (state.done) {
    return (
      <p role="status" className="text-green text-sm">
        {state.done}
      </p>
    );
  }
  return null;
}

/** Pause or resume automatic payouts; the reason is required and audited. */
export function PauseSwitchForm({ paused }: { paused: boolean }) {
  const [state, action, pending] = useActionState(switchAutomaticPayoutsAction, initial);
  const id = paused ? "resume-reason" : "pause-reason";
  return (
    <form action={action} className="space-y-2">
      <input type="hidden" name="intent" value={paused ? "resume" : "pause"} />
      <label htmlFor={id} className="block text-sm font-medium">
        {paused ? "Why are you resuming automatic payouts?" : "Why are you pausing them?"}
      </label>
      <textarea
        id={id}
        name="reason"
        required
        minLength={3}
        maxLength={500}
        rows={2}
        className="border-edge bg-raised w-full rounded-lg border px-3 py-2 text-sm"
      />
      <Button type="submit" disabled={pending} variant={paused ? "primary" : "danger"}>
        {paused ? "Resume automatic payouts" : "Pause automatic payouts"}
      </Button>
      <Feedback state={state} />
    </form>
  );
}

/** Move never-sent automatic payments back to the manual (maker-checker) path. */
export function ReleaseUnsentForm({ count }: { count: number }) {
  const [state, action, pending] = useActionState(releaseUnsentAction, initial);
  return (
    <form
      action={action}
      className="space-y-2"
      onSubmit={(event) => {
        if (!window.confirm("Move every unsent automatic payment to manual review?")) {
          event.preventDefault();
        }
      }}
    >
      <label htmlFor="release-reason" className="block text-sm font-medium">
        Why move the {count} unsent payment{count === 1 ? "" : "s"} to manual review?
      </label>
      <textarea
        id="release-reason"
        name="reason"
        required
        minLength={3}
        maxLength={500}
        rows={2}
        className="border-edge bg-raised w-full rounded-lg border px-3 py-2 text-sm"
      />
      <Button type="submit" disabled={pending} variant="ghost">
        Move unsent payments to manual review
      </Button>
      <Feedback state={state} />
    </form>
  );
}

/** Record how an alert was followed up. */
export function ResolveAlertForm({ alertId }: { alertId: string }) {
  const [state, action, pending] = useActionState(resolveAlertAction, initial);
  const id = `note-${alertId}`;
  return (
    <form action={action} className="space-y-2">
      <input type="hidden" name="alert_id" value={alertId} />
      <label htmlFor={id} className="block text-sm">
        What did you do about it?
      </label>
      <input
        id={id}
        name="note"
        required
        minLength={3}
        maxLength={500}
        className="border-edge bg-raised w-full rounded-lg border px-3 py-2 text-sm"
      />
      <Button type="submit" disabled={pending} variant="ghost">
        Mark as followed up
      </Button>
      <Feedback state={state} />
    </form>
  );
}
