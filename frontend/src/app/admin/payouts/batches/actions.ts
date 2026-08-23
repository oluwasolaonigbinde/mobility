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
  intent: z.enum(["approve", "submit", "retry_failed", "void"]),
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
    const endpoint = parsed.data.intent === "retry_failed" ? "retry-failed" : parsed.data.intent;
    await batchApi<PayoutBatch>(`/${parsed.data.batch_id}/${endpoint}`, {
      method: "POST",
    });
    revalidatePath("/admin/payouts/batches");
    return {
      done: {
        approve: "Batch approved by checker",
        submit: "Batch submitted to the configured provider",
        retry_failed: "Failed lines resubmitted with their frozen idempotency keys",
        void: "Pre-provider reservations released",
      }[parsed.data.intent],
    };
  } catch (error) {
    return { error: error instanceof Error ? error.message : "Could not update the batch" };
  }
}

const pollSchema = z.object({ line_id: z.string().uuid() });

export async function pollLineAction(
  _previous: BatchActionState,
  formData: FormData,
): Promise<BatchActionState> {
  const parsed = pollSchema.safeParse({ line_id: String(formData.get("line_id") ?? "") });
  if (!parsed.success) return { error: "Invalid payout line" };
  try {
    await batchApi<PayoutBatch>(`/lines/${parsed.data.line_id}/poll`, { method: "POST" });
    revalidatePath("/admin/payouts/batches");
    return { done: "Verified provider result applied to this line" };
  } catch (error) {
    return { error: error instanceof Error ? error.message : "Could not poll the payout line" };
  }
}

const debtSchema = z.object({
  driver_profile_id: z.string().uuid(),
  currency: z
    .string()
    .trim()
    .length(3)
    .transform((value) => value.toUpperCase()),
});

export async function allocateDebtAction(
  _previous: BatchActionState,
  formData: FormData,
): Promise<BatchActionState> {
  const parsed = debtSchema.safeParse({
    driver_profile_id: String(formData.get("driver_profile_id") ?? ""),
    currency: String(formData.get("currency") ?? ""),
  });
  if (!parsed.success) return { error: "Enter a valid driver profile ID and currency" };
  try {
    await batchApi(`/debt-balances/${parsed.data.driver_profile_id}/allocate`, {
      method: "POST",
      body: JSON.stringify({ currency: parsed.data.currency }),
    });
    revalidatePath("/admin/payouts/batches");
    return { done: "Available credits allocated to carry-forward debt" };
  } catch (error) {
    return { error: error instanceof Error ? error.message : "Could not allocate payout debt" };
  }
}
