"use client";

import { useActionState } from "react";
import { orderTransitionAction, type OrderActionState } from "./actions";
import { Button } from "@/components/ui/button";
import type { components } from "@/lib/api/schema";

type OrderStatus = components["schemas"]["PayoutCorrectionOrderStatus"];
const initialState: OrderActionState = {};

export function OrderActions({
  orderId,
  status,
  requiresReleaseAt,
}: {
  orderId: string;
  status: OrderStatus;
  requiresReleaseAt: boolean;
}) {
  const [state, formAction, pending] = useActionState(orderTransitionAction, initialState);
  return (
    <form action={formAction} className="flex flex-col items-end gap-2">
      <input type="hidden" name="order_id" value={orderId} />
      {status === "draft" ? (
        <>
          <label className="flex flex-col items-end gap-1">
            <span className="micro text-muted">Approval reason</span>
            <textarea
              name="reason"
              required
              minLength={3}
              maxLength={500}
              aria-label="Approval reason"
              className="border-edge bg-raised text-ink focus:border-amber rounded-lg border px-2.5 text-sm focus:outline-none"
            />
          </label>
          {requiresReleaseAt ? (
            <label className="flex flex-col items-end gap-1">
              <span className="micro text-muted">Make extra pay available at</span>
              <input
                name="release_at"
                type="datetime-local"
                required
                aria-label="Release at"
                className="border-edge bg-raised text-ink focus:border-amber h-9 rounded-lg border px-2.5 font-mono text-xs focus:outline-none"
              />
            </label>
          ) : null}
          <Button type="submit" disabled={pending} className="h-9 px-3 text-xs">
            {pending ? "Applying…" : "Approve and apply"}
          </Button>
        </>
      ) : (
        <p className="micro text-faint text-right">
          {status === "stale"
            ? "The saved preview has changed — prepare a new pay correction."
            : "Completed — the pay changes are recorded."}
        </p>
      )}
      {state.error ? (
        <p role="alert" className="text-coral max-w-[16rem] text-right text-xs">
          {state.error}
        </p>
      ) : null}
      {state.done && !state.error ? (
        <p className="text-green text-right text-xs">{state.done}</p>
      ) : null}
    </form>
  );
}
