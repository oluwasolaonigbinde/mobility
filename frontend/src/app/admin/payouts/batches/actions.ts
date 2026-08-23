"use server";

import { revalidatePath } from "next/cache";
import { z } from "zod";
import { batchApi, type PayoutBatch } from "./batch-api";

export interface BatchActionState {
  error?: string;
  done?: string;
}

const createSchema = z.object({
  currency: z
    .string()
    .trim()
    .length(3)
    .transform((value) => value.toUpperCase()),
  ledgerEntryIds: z.array(z.string().uuid()).min(1).max(500),
});

export async function createAndReserveBatchAction(
  _previous: BatchActionState,
  formData: FormData,
): Promise<BatchActionState> {
  const parsed = createSchema.safeParse({
    currency: String(formData.get("currency") ?? ""),
    ledgerEntryIds: String(formData.get("ledger_entry_ids") ?? "")
      .split(/[\s,]+/)
      .filter(Boolean),
  });
  if (!parsed.success) return { error: "Enter a currency and at least one valid ledger entry ID" };
  try {
    const draft = await batchApi<PayoutBatch>("", {
      method: "POST",
      body: JSON.stringify({ currency: parsed.data.currency }),
    });
    await batchApi<PayoutBatch>(`/${draft.id}/reserve`, {
      method: "POST",
      body: JSON.stringify({ ledger_entry_ids: parsed.data.ledgerEntryIds }),
    });
    revalidatePath("/admin/payouts/batches");
    return { done: "Batch reserved with frozen payout instructions" };
  } catch (error) {
    return { error: error instanceof Error ? error.message : "Could not reserve the batch" };
  }
}

const transitionSchema = z.object({
  batch_id: z.string().uuid(),
  intent: z.enum(["approve", "submit"]),
});

export async function batchTransitionAction(
  _previous: BatchActionState,
  formData: FormData,
): Promise<BatchActionState> {
  const parsed = transitionSchema.safeParse({
    batch_id: String(formData.get("batch_id") ?? ""),
    intent: String(formData.get("intent") ?? ""),
  });
  if (!parsed.success) return { error: "Invalid batch action" };
  try {
    await batchApi<PayoutBatch>(`/${parsed.data.batch_id}/${parsed.data.intent}`, {
      method: "POST",
    });
    revalidatePath("/admin/payouts/batches");
    return {
      done:
        parsed.data.intent === "approve"
          ? "Batch approved by checker"
          : "Batch submitted to the configured provider",
    };
  } catch (error) {
    return { error: error instanceof Error ? error.message : "Could not update the batch" };
  }
}
