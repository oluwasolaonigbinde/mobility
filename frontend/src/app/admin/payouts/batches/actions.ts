"use server";

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
  PAYOUT_BATCH_MAKER_CHECKER_REQUIRED:
    "The person preparing this payment run cannot approve it. Ask a different staff member to review it.",
  PAYOUT_BATCH_NOT_APPROVED:
    "A different staff member must approve the payment run before submission.",
  PAYOUT_RECONCILER_SEPARATION_REQUIRED:
    "Manual verification requires a staff member other than the person preparing it and the second reviewer.",
  PAYOUT_ENTRY_HELD: "A selected credit is now held for review. Refresh available earnings.",
  PAYOUT_ASSESSMENT_NOT_CURRENT:
    "A selected credit needs a current successful assessment. Refresh available earnings.",
  PAYOUT_DEBT_ALLOCATION_REQUIRED:
    "Carry-forward debt must be allocated first. Refresh available earnings.",
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
});

export async function createAndReserveBatchAction(
  _previous: BatchActionState,
  formData: FormData,
): Promise<BatchActionState> {
  const parsed = createSchema.safeParse({
    requestId: String(formData.get("request_id") ?? ""),
    currency: String(formData.get("currency") ?? ""),
    ledgerEntryIds: String(formData.get("ledger_entry_ids") ?? "")
      .split(/[\s,]+/)
      .filter(Boolean),
  });
  if (!parsed.success)
    return { error: "Select a currency and at least one available earnings record." };
  try {
    const draft = await batchApi<PayoutBatch>("", {
      method: "POST",
      body: JSON.stringify({ currency: parsed.data.currency, request_id: parsed.data.requestId }),
    });
    const reserved = await batchApi<PayoutBatch>(`/${draft.id}/reserve`, {
      method: "POST",
      body: JSON.stringify({ ledger_entry_ids: parsed.data.ledgerEntryIds }),
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
});

export async function batchTransitionAction(
  _previous: BatchActionState,
  formData: FormData,
): Promise<BatchActionState> {
  const parsed = transitionSchema.safeParse({
    batch_id: String(formData.get("batch_id") ?? ""),
    intent: String(formData.get("intent") ?? ""),
  });
  if (!parsed.success) return { error: "Invalid payment run action" };
  try {
    const endpoint = parsed.data.intent === "retry_failed" ? "retry-failed" : parsed.data.intent;
    const result = await batchApi<PayoutBatch>(`/${parsed.data.batch_id}/${endpoint}`, {
      method: "POST",
    });
    revalidatePath("/admin/money");
    return {
      done: {
        approve: "Payment run approved by the second reviewer",
        submit:
          "Submission queued. This does not confirm submission or payment; check each payment for provider evidence.",
        retry_failed:
          "Replacement reserved. Review its saved instructions and obtain independent approval before submission.",
        void: "Unsent payment reservations released",
      }[parsed.data.intent],
      ...(parsed.data.intent === "retry_failed" ? { batchId: result.id } : {}),
    };
  } catch (error) {
    return {
      error: publicActionError(
        error,
        moneyErrors,
        "The update could not be confirmed. Refresh this payment run before retrying.",
      ),
    };
  }
}

const pollSchema = z.object({ line_id: z.string().uuid() });

export async function pollLineAction(
  _previous: BatchActionState,
  formData: FormData,
): Promise<BatchActionState> {
  const parsed = pollSchema.safeParse({ line_id: String(formData.get("line_id") ?? "") });
  if (!parsed.success) return { error: "Invalid selected payment" };
  try {
    await batchApi<PayoutBatch>(`/lines/${parsed.data.line_id}/poll`, { method: "POST" });
    revalidatePath("/admin/money");
    return { done: "Verified provider result applied to this payment" };
  } catch (error) {
    return {
      error: publicActionError(
        error,
        moneyErrors,
        "No verified result could be confirmed. The current payment status remains authoritative.",
      ),
    };
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
  if (!parsed.success) return { error: "Select a driver and currency." };
  try {
    await batchApi(`/debt-balances/${parsed.data.driver_profile_id}/allocate`, {
      method: "POST",
      body: JSON.stringify({ currency: parsed.data.currency }),
    });
    revalidatePath("/admin/money");
    return { done: "Available credits allocated to carry-forward debt" };
  } catch (error) {
    return {
      error: publicActionError(
        error,
        moneyErrors,
        "The allocation could not be confirmed. Refresh the driver's credits before retrying.",
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
    return {
      error:
        error instanceof ApiError && error.status === 403
          ? "Administrator access is required."
          : "Destination details are unavailable. No payment has been authorized.",
    };
  }
}
