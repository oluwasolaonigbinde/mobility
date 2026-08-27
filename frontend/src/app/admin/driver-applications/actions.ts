"use server";

import { revalidatePath } from "next/cache";
import { z } from "zod";
import { createApiClient } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import { getSessionToken } from "@/lib/auth/session";

export interface PersonPayeeDecisionState {
  error?: string;
  done?: string;
}

const schema = z.object({
  application_id: z.string().uuid(),
  client_request_id: z.string().uuid(),
  intent: z.enum(["approve", "reject", "expire"]),
  reason_code: z
    .enum([
      "missing_evidence",
      "rejected_evidence",
      "expired_evidence",
      "unsafe_evidence",
      "identity_mismatch",
      "bank_account_mismatch",
      "unreadable_evidence",
    ])
    .optional(),
  identity_match_confirmed: z.boolean(),
  bank_account_match_confirmed: z.boolean(),
  documents_readable_confirmed: z.boolean(),
});

export async function reviewPersonPayeeAction(
  _previous: PersonPayeeDecisionState,
  formData: FormData,
): Promise<PersonPayeeDecisionState> {
  const intent = String(formData.get("intent") ?? "");
  const parsed = schema.safeParse({
    application_id: String(formData.get("application_id") ?? ""),
    client_request_id: String(formData.get("client_request_id") ?? ""),
    intent,
    reason_code:
      intent === "approve"
        ? undefined
        : intent === "expire"
          ? "expired_evidence"
          : String(formData.get("reason_code") ?? ""),
    identity_match_confirmed: formData.get("identity_match_confirmed") === "on",
    bank_account_match_confirmed: formData.get("bank_account_match_confirmed") === "on",
    documents_readable_confirmed: formData.get("documents_readable_confirmed") === "on",
  });
  if (!parsed.success) {
    return { error: parsed.error.issues[0]?.message ?? "Invalid person/payee decision." };
  }
  if (
    parsed.data.intent === "approve" &&
    !(
      parsed.data.identity_match_confirmed &&
      parsed.data.bank_account_match_confirmed &&
      parsed.data.documents_readable_confirmed
    )
  ) {
    return { error: "Confirm identity, account match and document readability before approval." };
  }
  const decision =
    parsed.data.intent === "approve"
      ? "approved"
      : parsed.data.intent === "expire"
        ? "expired"
        : "rejected";
  const reasonCode =
    decision === "approved" ? "complete_current_evidence" : parsed.data.reason_code;
  if (!reasonCode) return { error: "Select a reason for this decision." };
  try {
    await createApiClient(await getSessionToken()).POST(
      "/api/v1/admin/driver-applications/{application_id}/person-payee-decision",
      {
        params: { path: { application_id: parsed.data.application_id } },
        body: {
          client_request_id: parsed.data.client_request_id,
          decision,
          reason_code: reasonCode,
          identity_match_confirmed: parsed.data.identity_match_confirmed,
          bank_account_match_confirmed: parsed.data.bank_account_match_confirmed,
          documents_readable_confirmed: parsed.data.documents_readable_confirmed,
        },
      },
    );
  } catch (error) {
    if (error instanceof ApiError) return { error: error.message };
    return { error: "Could not reach the onboarding service." };
  }
  revalidatePath("/admin/driver-applications");
  return { done: `Person/payee evidence ${decision}.` };
}
