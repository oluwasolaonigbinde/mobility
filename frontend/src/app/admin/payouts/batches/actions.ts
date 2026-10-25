"use server";

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
    return { error: "Select available credits in one currency." };
  }
  try {
    return await batchApi<{ currency: string; total_amount: string }>("/selection-preview", {
      method: "POST",
      body: JSON.stringify({ currency, ledger_entry_ids: ledgerEntryIds }),
    });
  } catch (error) {
    unstable_rethrow(error);
    return {
      error: publicActionError(
        error,
        moneyErrors,
        "Selection could not be verified. Refresh available earnings.",
      ),
    };
  }
}

const moneyErrors: Record<string, string> = {
  DISBURSEMENT_PROVIDER_UNAVAILABLE:
    "Automated submission is not configured. No transfer is confirmed.",
  PAYOUT_BATCH_NOT_APPROVED: "An admin must approve the payment run before submission.",
  PAYOUT_ENTRY_HELD: "A selected credit is now held for review. Refresh available earnings.",
  PAYOUT_ASSESSMENT_NOT_CURRENT:
    "A selected credit needs a current successful assessment. Refresh available earnings.",
  PAYOUT_ENTRY_ALREADY_RESERVED:
    "A selected earning is already reserved for a payment run. Open that payment run.",
  PAYOUT_ENTRY_INELIGIBLE: "A selected credit is no longer eligible. Refresh available earnings.",
  PAYOUT_BATCH_NOT_DRAFT:
    "This draft was already reserved with different earnings. Open the existing payment run.",
  PAYOUT_DRAFT_RETRY_CONFLICT:
    "This recovery reference cannot be reused. Open your existing draft.",
  PAYOUT_PAYEE_VERSION_STALE:
    "The bank details changed. Refresh and review the current bank details.",
  PAYOUT_BANK_ACCOUNT_UNVERIFIED:
    "The bank details require verification by an authorized staff member.",
  PAYOUT_RESOLVED_LINES_NOT_RETRYABLE:
    "A failed payment requires a newer verified bank version with a different bank or account number. Replacing the encrypted record or entering the same bank details does not allow a replacement payment.",
  PAYOUT_UNRESOLVED_LINES_REMAIN:
    "Wait for verified results on every payment sent to the provider before requesting a replacement.",
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
    const reserved = await batchApi<PayoutBatch>(`/${draft.id}/reserve`, {
      method: "POST",
      body: JSON.stringify({
        ledger_entry_ids: parsed.data.ledgerEntryIds,
        reason: parsed.data.reason,
      }),
    });
    revalidatePath("/admin/money");
    return {
      done:
        reserved.status === "reserved"
          ? "Reservation confirmed. Open the payment run to review its current status."
          : "Existing payment run recovered; no new reservation was created. Open the payment run to review its current status.",
      batchId: draft.id,
    };
  } catch (error) {
    unstable_rethrow(error);
    return {
      error: publicActionError(
        error,
        moneyErrors,
        "The response could not be confirmed. Retry this saved request or open its draft; do not start a second payment run.",
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
  if (!parsed.success) return { error: "Invalid payment run action" };
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
        submit:
          "Submission queued. This does not confirm submission or payment; check each payment for provider evidence.",
        retry_failed:
          "Replacement reserved. Review its saved instructions and approve it with a reason before submission.",
        void: "Unsent payment reservations released",
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
  if (!parsed.success) return { error: "Invalid selected payment" };
  try {
    await batchApi<PayoutBatch>(`/lines/${parsed.data.line_id}/poll`, {
      method: "POST",
      body: JSON.stringify({ reason: parsed.data.reason }),
    });
    revalidatePath("/admin/money");
    return { done: "Verified provider result applied to this payment" };
  } catch (error) {
    unstable_rethrow(error);
    return {
      error: publicActionError(
        error,
        moneyErrors,
        "No verified result could be confirmed. The current payment status remains authoritative.",
      ),
    };
  }
}

export async function maskedDestinationAction(
  versionId: string,
): Promise<{ mask?: string; error?: string }> {
  if (!z.string().uuid().safeParse(versionId).success)
    return { error: "Select a verified destination." };
  try {
    const api = createApiClient(await getSessionToken());
    const { data } = await api.POST(
      "/api/v1/admin/payees/bank-account-versions/{version_id}/reveal",
      {
        params: { path: { version_id: versionId } },
        body: { purpose: "payout_destination_review" },
      },
    );
    if (!data) return { error: "Destination could not be verified." };
    return { mask: `Bank ${data.bank_code} · account ending ${data.account_number.slice(-4)}` };
  } catch (error) {
    unstable_rethrow(error);
    return {
      error:
        error instanceof ApiError && error.status === 403
          ? "Administrator access is required."
          : "Destination details are unavailable. No payment has been authorized.",
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
    return { done: "Negative adjustment recorded. Other trips' pay is unchanged." };
  } catch (error) {
    unstable_rethrow(error);
    return {
      error:
        error instanceof ApiError
          ? publicActionError(error)
          : "No result was confirmed. Retry the same adjustment or check the ledger.",
    };
  }
}
