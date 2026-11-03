"use server";

import { bankDisplayName } from "@/lib/driver/bank-name";
import { unstable_rethrow } from "next/navigation";

import { revalidatePath } from "next/cache";
import { z } from "zod";
import { batchApi, type PayoutBatch } from "./batch-api";
import { ApiError } from "@/lib/api/errors";
import { createApiClient } from "@/lib/api/client";
import { getSessionToken } from "@/lib/auth/session";
import { publicActionError } from "@/lib/api/public-action-error";

export interface BatchActionState {
  error?: string;
  done?: string;
  batchId?: string;
}

export async function previewSelectionAction(
  currency: string,
  ledgerEntryIds: string[],
): Promise<{
  currency?: string;
  total_amount?: string;
  earnings_amount?: string;
  deduction_amount?: string;
  error?: string;
}> {
  if (
    !z
      .object({
        currency: z.string().regex(/^[A-Z]{3}$/),
        ledgerEntryIds: z.array(z.string().uuid()).min(1).max(100),
      })
      .safeParse({ currency, ledgerEntryIds }).success
  ) {
    return { error: "Select payments in one currency." };
  }
  try {
    return await batchApi<{ currency: string; total_amount: string }>("/selection-preview", {
      method: "POST",
      body: JSON.stringify({ currency, ledger_entry_ids: ledgerEntryIds }),
    });
  } catch (error) {
    unstable_rethrow(error);
    return {
      error: publicActionError(error, moneyErrors, "Refresh the list and select again."),
    };
  }
}

const moneyErrors: Record<string, string> = {
  DISBURSEMENT_PROVIDER_UNAVAILABLE: "Run saved, not sent. Payments are not connected.",
  PAYOUT_BATCH_NOT_APPROVED: "An admin must approve the payment run before submission.",
  PAYOUT_ENTRY_HELD: "A selected payment is now on hold. Refresh the list.",
  PAYOUT_ASSESSMENT_NOT_CURRENT: "A selected payment needs checking. Refresh the list.",
  PAYOUT_ENTRY_ALREADY_RESERVED:
    "A selected earning is already reserved for a payment run. Open that payment run.",
  PAYOUT_ENTRY_INELIGIBLE: "A selected payment is no longer ready. Refresh the list.",
  PAYOUT_BATCH_NOT_DRAFT: "This payment run has changed. Refresh and start again.",
  PAYOUT_DRAFT_RETRY_CONFLICT: "This payment run has changed. Refresh and start again.",
  PAYOUT_PAYEE_VERSION_STALE:
    "The bank details changed. Refresh and review the current bank details.",
  PAYOUT_BANK_ACCOUNT_UNVERIFIED:
    "The bank details require verification by an authorized staff member.",
  PAYOUT_RESOLVED_LINES_NOT_RETRYABLE:
    "Bank details must change before this payment can be sent again.",
  PAYOUT_UNRESOLVED_LINES_REMAIN: "Wait for the result on every payment first.",
  PAYOUT_FAILED_LINES_MISSING: "This payment run has no failed payments to replace.",
  FORBIDDEN_ROLE: "Your account no longer has administrator access.",
};

const createSchema = z.object({
  currency: z
    .string()
    .trim()
    .length(3)
    .transform((value) => value.toUpperCase()),
  ledgerEntryIds: z.array(z.string().uuid()).min(1).max(500),
  requestId: z.string().uuid(),
  reason: z.string().trim().min(3).max(500),
});

export async function createAndReserveBatchAction(
  _previous: BatchActionState,
  formData: FormData,
): Promise<BatchActionState> {
  const parsed = createSchema.safeParse({
    requestId: String(formData.get("request_id") ?? ""),
    reason: String(formData.get("reason") ?? ""),
    currency: String(formData.get("currency") ?? ""),
    ledgerEntryIds: String(formData.get("ledger_entry_ids") ?? "")
      .split(/[\s,]+/)
      .filter(Boolean),
  });
  if (!parsed.success)
    return {
      error: "Select a currency, available earnings and a reason between 3 and 500 characters.",
    };
  try {
    const draft = await batchApi<PayoutBatch>("", {
      method: "POST",
      body: JSON.stringify({
        currency: parsed.data.currency,
        request_id: parsed.data.requestId,
        reason: parsed.data.reason,
      }),
    });
    const reserved = await batchApi<PayoutBatch | { outcome: "nothing_to_send"; message: string }>(
      `/${draft.id}/reserve`,
      {
        method: "POST",
        body: JSON.stringify({
          ledger_entry_ids: parsed.data.ledgerEntryIds,
          reason: parsed.data.reason,
        }),
      },
    );
    revalidatePath("/admin/money");
    if ("outcome" in reserved) return { done: reserved.message };
    return {
      done:
        reserved.status === "reserved"
          ? "Payment run created."
          : "This payment run already exists.",
      batchId: draft.id,
    };
  } catch (error) {
    unstable_rethrow(error);
    return {
      error: publicActionError(
        error,
        moneyErrors,
        "We couldn't confirm that. Check the list before starting another payment run.",
      ),
      batchId: parsed.data.requestId,
    };
  }
}

const transitionSchema = z.object({
  batch_id: z.string().uuid(),
  intent: z.enum(["approve", "submit", "retry_failed", "void"]),
  reason: z.string().trim().max(500),
});

export async function batchTransitionAction(
  _previous: BatchActionState,
  formData: FormData,
): Promise<BatchActionState> {
  const parsed = transitionSchema.safeParse({
    batch_id: String(formData.get("batch_id") ?? ""),
    intent: String(formData.get("intent") ?? ""),
    reason: String(formData.get("reason") ?? ""),
  });
  if (!parsed.success) return { error: "Something went wrong. Refresh and try again." };
  const needsReason = parsed.data.intent === "approve" || parsed.data.intent === "retry_failed";
  if (needsReason && parsed.data.reason.length < 3)
    return { error: "Give a reason between 3 and 500 characters." };
  try {
    const endpoint = parsed.data.intent === "retry_failed" ? "retry-failed" : parsed.data.intent;
    const result = await batchApi<PayoutBatch>(`/${parsed.data.batch_id}/${endpoint}`, {
      method: "POST",
      ...(needsReason ? { body: JSON.stringify({ reason: parsed.data.reason }) } : {}),
    });
    revalidatePath("/admin/money");
    return {
      done: {
        approve: "Payment run approved",
        submit: "Sending started. Check each payment for the result.",
        retry_failed: "Replacement ready. Approve it to send.",
        void: "Payment run cancelled.",
      }[parsed.data.intent],
      ...(parsed.data.intent === "retry_failed" ? { batchId: result.id } : {}),
    };
  } catch (error) {
    unstable_rethrow(error);
    return {
      error: publicActionError(
        error,
        moneyErrors,
        "The update could not be confirmed. Refresh this payment run before retrying.",
      ),
    };
  }
}

const pollSchema = z.object({
  line_id: z.string().uuid(),
  reason: z.string().trim().min(3).max(500),
});

export async function pollLineAction(
  _previous: BatchActionState,
  formData: FormData,
): Promise<BatchActionState> {
  const parsed = pollSchema.safeParse({
    line_id: String(formData.get("line_id") ?? ""),
    reason: String(formData.get("reason") ?? ""),
  });
  if (!parsed.success) return { error: "Something went wrong. Refresh and try again." };
  try {
    await batchApi<PayoutBatch>(`/lines/${parsed.data.line_id}/poll`, {
      method: "POST",
      body: JSON.stringify({ reason: parsed.data.reason }),
    });
    revalidatePath("/admin/money");
    return { done: "Payment result added." };
  } catch (error) {
    unstable_rethrow(error);
    return {
      error: publicActionError(error, moneyErrors, "No confirmed payment result yet."),
    };
  }
}

export async function maskedDestinationAction(
  versionId: string,
): Promise<{ mask?: string; error?: string }> {
  if (!z.string().uuid().safeParse(versionId).success)
    return { error: "Select a checked bank account." };
  try {
    const api = createApiClient(await getSessionToken());
    const { data } = await api.POST(
      "/api/v1/admin/payees/bank-account-versions/{version_id}/reveal",
      {
        params: { path: { version_id: versionId } },
        body: { purpose: "payout_destination_review" },
      },
    );
    if (!data) return { error: "We couldn't check this bank account." };
    return {
      mask: `${bankDisplayName(data.bank_code)} · account ending ${data.account_number.slice(-4)}`,
    };
  } catch (error) {
    unstable_rethrow(error);
    return {
      error:
        error instanceof ApiError && error.status === 403
          ? "Administrator access is required."
          : "Bank details can't be shown. Nothing was approved.",
    };
  }
}

const adjustmentSchema = z.object({
  entry_id: z.string().uuid(),
  request_id: z.string().uuid(),
  currency: z.string().regex(/^[A-Z]{3}$/),
  amount: z
    .string()
    .trim()
    .regex(/^(?:0|[1-9]\d{0,11})(?:\.\d{1,2})?$/)
    .refine((value) => /[1-9]/.test(value), "Enter a positive amount"),
  reason: z.string().trim().min(3).max(500),
});

export async function negativeAdjustmentAction(
  _previous: BatchActionState,
  form: FormData,
): Promise<BatchActionState> {
  const parsed = adjustmentSchema.safeParse(Object.fromEntries(form));
  if (!parsed.success)
    return { error: "Enter a positive amount and a reason between 3 and 500 characters." };
  const { entry_id, ...body } = parsed.data;
  const rawDay = String(form.get("lagos_day") ?? "").trim();
  if (rawDay && !/^\d{4}-\d{2}-\d{2}$/.test(rawDay))
    return { error: "Choose a valid Nigeria day." };
  try {
    const api = createApiClient(await getSessionToken());
    await api.POST("/api/v1/admin/earnings-ledger/{entry_id}/negative-adjustments", {
      params: { path: { entry_id } },
      body: { ...body, lagos_day: rawDay || null },
    });
    revalidatePath("/admin/money");
    return { done: "Deduction recorded." };
  } catch (error) {
    unstable_rethrow(error);
    return {
      error:
        error instanceof ApiError
          ? publicActionError(error)
          : "We couldn't confirm this. Check the trip's pay before trying again.",
    };
  }
}
