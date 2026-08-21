"use client";

import { useActionState } from "react";
import { newOrderAction, type NewOrderState } from "./actions";
import { Button } from "@/components/ui/button";
import { formatMoneyExact } from "@/lib/format";

const initialState: NewOrderState = {};

export function NewOrderForm({ campaigns }: { campaigns: { id: string; name: string }[] }) {
  const [state, formAction, pending] = useActionState(newOrderAction, initialState);
  const p = state.projection;

  return (
    <form action={formAction} className="flex flex-col gap-4" noValidate>
      <div className="grid gap-4 sm:grid-cols-3">
        <div className="flex flex-col gap-1.5">
          <label htmlFor="co-campaign" className="micro text-muted">
            Campaign
          </label>
          <select
            id="co-campaign"
            name="campaign_id"
            className="border-edge bg-raised text-ink focus:border-amber h-11 rounded-lg border px-3.5 text-sm focus:outline-none"
          >
            {campaigns.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </select>
        </div>
        <div className="flex flex-col gap-1.5">
          <label htmlFor="co-day" className="micro text-muted">
            Lagos day
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
            Reason (audited)
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
          ✓ Draft order created — submit it below for independent approval.
        </p>
      ) : null}

      {p ? (
        <div className="border-edge bg-raised/50 rounded-lg border px-4 py-3">
          <p className="micro text-muted mb-2">
            Projected delta (read-only preview — the order re-projects on creation)
          </p>
          <dl className="grid grid-cols-2 gap-x-4 gap-y-1 font-mono text-xs sm:grid-cols-4">
            <dt className="text-faint">Posted today</dt>
            <dd>{formatMoneyExact(p.previousTotal, p.currency)}</dd>
            <dt className="text-faint">Correct total</dt>
            <dd>{formatMoneyExact(p.targetTotal, p.currency)}</dd>
            <dt className="text-faint">Delta</dt>
            <dd className={p.deltaTotal.startsWith("-") ? "text-coral" : "text-green"}>
              {formatMoneyExact(p.deltaTotal, p.currency)}
            </dd>
            <dt className="text-faint">Trips</dt>
            <dd>
              {p.tripCount} ({p.adjustmentCount} up · {p.reversalCount} down)
            </dd>
          </dl>
          <p className="micro text-faint mt-2 break-all">projection {p.fingerprint}</p>
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
          {pending ? "Working…" : "Preview delta"}
        </Button>
        <Button type="submit" name="intent" value="create" disabled={pending} className="flex-1">
          {pending ? "Working…" : "Create draft order"}
        </Button>
      </div>
      <p className="micro text-faint">
        Direct day recompute is retired — corrections execute only through an approved order
        (creator ≠ approver). Positive deltas release to drivers at the date set on execution.
      </p>
    </form>
  );
}
