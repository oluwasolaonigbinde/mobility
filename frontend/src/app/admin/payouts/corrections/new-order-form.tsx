"use client";

import { useActionState } from "react";
import { newOrderAction, type NewOrderState } from "./actions";
import { Button } from "@/components/ui/button";
import { SearchSelect } from "../../search-select";
import { formatMoneyExact } from "@/lib/format";

const initialState: NewOrderState = {};

export function NewOrderForm() {
  const [state, formAction, pending] = useActionState(newOrderAction, initialState);
  const p = state.projection;

  return (
    <form action={formAction} className="flex flex-col gap-4" noValidate>
      <div className="grid gap-4 sm:grid-cols-3">
        <SearchSelect kind="campaign" name="campaign_id" label="Campaign" />
        <div className="flex flex-col gap-1.5">
          <label htmlFor="co-day" className="micro text-muted">
            Day, Nigeria time (WAT)
          </label>
          <input
            id="co-day"
            name="lagos_day"
            type="date"
            className="border-edge bg-raised text-ink focus:border-amber h-11 rounded-lg border px-3.5 font-mono text-sm focus:outline-none"
          />
        </div>
        <div className="flex flex-col gap-1.5">
          <label htmlFor="co-reason" className="micro text-muted">
            Reason (logged)
          </label>
          <input
            id="co-reason"
            name="reason"
            placeholder="why this day needs correcting"
            className="border-edge bg-raised text-ink placeholder:text-faint focus:border-amber h-11 rounded-lg border px-3.5 text-sm focus:outline-none"
          />
        </div>
      </div>

      {state.error ? (
        <p
          role="alert"
          className="border-coral/40 bg-coral/10 text-coral rounded-lg border px-3.5 py-2.5 text-sm"
        >
          {state.error}
        </p>
      ) : null}
      {state.created && !state.error ? (
        <p className="border-green/40 bg-green/10 text-green rounded-lg border px-3.5 py-2.5 text-sm">
          ✓ Pay correction created — open it in the list and submit it for a second approval.
        </p>
      ) : null}

      {p ? (
        <div className="border-edge bg-raised/50 rounded-lg border px-4 py-3">
          <p className="micro text-muted mb-2">
            Expected pay change (preview; checked again when saved)
          </p>
          <dl className="grid grid-cols-2 gap-x-4 gap-y-1 font-mono text-xs sm:grid-cols-4">
            <dt className="text-faint">Current total</dt>
            <dd>{formatMoneyExact(p.previousTotal, p.currency)}</dd>
            <dt className="text-faint">Correct total</dt>
            <dd>{formatMoneyExact(p.targetTotal, p.currency)}</dd>
            <dt className="text-faint">Change</dt>
            <dd className={p.deltaTotal.startsWith("-") ? "text-coral" : "text-green"}>
              {formatMoneyExact(p.deltaTotal, p.currency)}
            </dd>
            <dt className="text-faint">Trips</dt>
            <dd>
              {p.tripCount} ({p.adjustmentCount} up · {p.reversalCount} down)
            </dd>
          </dl>
          <details className="micro text-faint mt-2 break-all">
            <summary>Recorded preview details</summary>
            {p.fingerprint}
          </details>
        </div>
      ) : null}

      <div className="flex gap-2">
        <Button
          type="submit"
          name="intent"
          value="project"
          disabled={pending}
          className="flex-1"
          variant="ghost"
        >
          {pending ? "Working…" : "Preview change"}
        </Button>
        <Button type="submit" name="intent" value="create" disabled={pending} className="flex-1">
          {pending ? "Working…" : "Create pay correction"}
        </Button>
      </div>
      <p className="micro text-faint">
        A different staff member must approve each correction. Extra pay becomes available to
        drivers on the date chosen when the correction runs.
      </p>
    </form>
  );
}
