"use client";

import { useActionState, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { negativeAdjustmentAction, type BatchActionState } from "./actions";

export function NegativeAdjustmentForm({
  entryId,
  currency,
}: {
  entryId: string;
  currency: string;
}) {
  const requestId = useRef<string | null>(null);
  const [day, setDay] = useState("");
  const [amount, setAmount] = useState("");
  const [reason, setReason] = useState("");
  const [state, action, pending] = useActionState(
    async (previous: BatchActionState, form: FormData) => {
      requestId.current ??= crypto.randomUUID();
      form.set("request_id", requestId.current);
      return negativeAdjustmentAction(previous, form);
    },
    {},
  );
  return (
    <details className="mt-3 text-sm">
      <summary>Record a negative adjustment</summary>
      <form action={action} className="mt-2 space-y-2">
        <p>This records a correction on this trip. It does not take money from another trip.</p>
        <input type="hidden" name="entry_id" value={entryId} />
        <input type="hidden" name="currency" value={currency} />
        <label className="block">
          Nigeria day (required if the trip spans days)
          <input
            name="lagos_day"
            type="date"
            value={day}
            onChange={(event) => setDay(event.target.value)}
            aria-label="Adjustment day"
            className="border-edge bg-raised text-ink block rounded border p-2"
          />
        </label>
        <label className="block">
          Amount to subtract ({currency})
          <input
            name="amount"
            required
            inputMode="decimal"
            value={amount}
            onChange={(event) => setAmount(event.target.value)}
            aria-label="Amount to subtract"
            className="border-edge bg-raised text-ink block rounded border p-2"
          />
        </label>
        <label className="block">
          Adjustment reason
          <textarea
            name="reason"
            required
            value={reason}
            onChange={(event) => setReason(event.target.value)}
            minLength={3}
            maxLength={500}
            aria-label="Adjustment reason"
            className="border-edge bg-raised text-ink block w-full rounded border p-2"
          />
        </label>
        <Button type="submit" disabled={pending || !!state.done} variant="ghost">
          {pending ? "Recording…" : "Record negative adjustment"}
        </Button>
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
    </details>
  );
}
