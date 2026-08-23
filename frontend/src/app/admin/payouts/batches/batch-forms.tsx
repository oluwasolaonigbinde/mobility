"use client";

import { useActionState } from "react";
import { Button } from "@/components/ui/button";
import {
  batchTransitionAction,
  createAndReserveBatchAction,
  type BatchActionState,
} from "./actions";

const initialState: BatchActionState = {};

export function CreateBatchForm() {
  const [state, action, pending] = useActionState(createAndReserveBatchAction, initialState);
  return (
    <form action={action} className="grid gap-3 sm:grid-cols-[8rem_1fr_auto]">
      <input
        name="currency"
        defaultValue="NGN"
        aria-label="Currency"
        className="border-edge bg-raised rounded-lg border px-3 text-sm uppercase"
      />
      <input
        name="ledger_entry_ids"
        aria-label="Ledger entry IDs"
        placeholder="Available ledger UUIDs, separated by commas"
        className="border-edge bg-raised rounded-lg border px-3 text-sm"
      />
      <Button type="submit" disabled={pending}>
        {pending ? "Reserving…" : "Create and reserve"}
      </Button>
      {state.error ? <p className="text-coral text-sm sm:col-span-3">{state.error}</p> : null}
      {state.done ? <p className="text-green text-sm sm:col-span-3">{state.done}</p> : null}
    </form>
  );
}

export function BatchActions({ batchId }: { batchId: string }) {
  const [state, action, pending] = useActionState(batchTransitionAction, initialState);
  return (
    <form action={action} className="flex flex-wrap justify-end gap-2">
      <input type="hidden" name="batch_id" value={batchId} />
      <Button type="submit" name="intent" value="approve" disabled={pending} variant="ghost">
        Approve
      </Button>
      <Button type="submit" name="intent" value="submit" disabled={pending}>
        Submit
      </Button>
      {state.error ? <p className="text-coral w-full text-xs">{state.error}</p> : null}
      {state.done ? <p className="text-green w-full text-xs">{state.done}</p> : null}
    </form>
  );
}
