"use client";

import { useActionState } from "react";
import { orderTransitionAction, type OrderActionState } from "./actions";
import { Button } from "@/components/ui/button";
import type { components } from "@/lib/api/schema";

type OrderStatus = components["schemas"]["PayoutCorrectionOrderStatus"];

const initialState: OrderActionState = {};

/**
 * Status-driven actions for one correction order. Buttons are disabled only
 * where the API is known to 403 (Q22: creator submits own draft; approver
 * must differ from creator). Everything else is attempted and the server's
 * verdict is rendered verbatim — the backend is the authority.
 */
export function OrderActions({
  orderId,
  status,
  isCreator,
  requiresReleaseAt,
}: {
  orderId: string;
  status: OrderStatus;
  isCreator: boolean;
  /** True when the stored projection contains positive per-trip deltas. */
  requiresReleaseAt: boolean;
}) {
  const [state, formAction, pending] = useActionState(orderTransitionAction, initialState);

  const terminalNote =
    status === "stale"
      ? "Projection drifted — this order is void; project a new one."
      : status === "executed"
        ? "Executed — differentials are in the ledger."
        : status === "rejected"
          ? "Rejected."
          : null;

  return (
    <form action={formAction} className="flex flex-col items-end gap-2">
      <input type="hidden" name="order_id" value={orderId} />

      {status === "draft" ? (
        <>
          <Button
            type="submit"
            name="intent"
            value="submit"
            variant="ghost"
            disabled={pending || !isCreator}
            className="h-9 px-3 text-xs"
          >
            Submit for approval
          </Button>
          {!isCreator ? (
            <p className="micro text-faint">Only the creator may submit this draft.</p>
          ) : null}
        </>
      ) : null}

      {status === "pending_approval" ? (
        <>
          <div className="flex gap-2">
            <Button
              type="submit"
              name="intent"
              value="approve"
              disabled={pending || isCreator}
              className="h-9 px-3 text-xs"
            >
              Approve
            </Button>
            <Button
              type="submit"
              name="intent"
              value="reject"
              variant="danger"
              disabled={pending}
              className="h-9 px-3 text-xs"
            >
              Reject
            </Button>
          </div>
          {isCreator ? (
            <p className="micro text-faint">Maker-checker: a different admin must approve.</p>
          ) : null}
        </>
      ) : null}

      {status === "approved" ? (
        <>
          {requiresReleaseAt ? (
            <label className="flex flex-col items-end gap-1">
              <span className="micro text-muted">Release positive deltas at</span>
              <input
                name="release_at"
                type="datetime-local"
                required
                aria-label="Release at"
                className="border-edge bg-raised text-ink focus:border-amber h-9 rounded-lg border px-2.5 font-mono text-xs focus:outline-none"
              />
            </label>
          ) : null}
          <Button
            type="submit"
            name="intent"
            value="execute"
            disabled={pending}
            className="h-9 px-3 text-xs"
          >
            Execute
          </Button>
        </>
      ) : null}

      {terminalNote ? <p className="micro text-faint text-right">{terminalNote}</p> : null}

      {state.error ? (
        <p role="alert" className="text-coral max-w-[16rem] text-right text-xs">
          {state.error}
        </p>
      ) : null}
      {state.done && !state.error ? (
        <p className="text-green text-right text-xs">✓ {state.done}</p>
      ) : null}
    </form>
  );
}
