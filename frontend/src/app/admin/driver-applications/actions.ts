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

export interface PersonPayeeEvidenceState {
  error?: string;
  done?: string;
  sensitiveValue?: string;
  downloadUrl?: string;
}

const evidenceSchema = z.discriminatedUnion("kind", [
  z.object({ kind: z.literal("nin"), submission_id: z.string().uuid() }),
  z.object({ kind: z.literal("account"), bank_account_version_id: z.string().uuid() }),
  z.object({
    kind: z.literal("document"),
    file_id: z.string().uuid(),
    submission_id: z.string().uuid(),
  }),
]);

export async function reviewPersonPayeeEvidenceAction(
  _previous: PersonPayeeEvidenceState,
  formData: FormData,
): Promise<PersonPayeeEvidenceState> {
  const parsed = evidenceSchema.safeParse({
    kind: String(formData.get("kind") ?? ""),
    submission_id: String(formData.get("submission_id") ?? ""),
    bank_account_version_id: String(formData.get("bank_account_version_id") ?? ""),
    file_id: String(formData.get("file_id") ?? ""),
  });
  if (!parsed.success) return { error: "The exact review evidence is unavailable." };
  const api = createApiClient(await getSessionToken());
  try {
    if (parsed.data.kind === "nin") {
      const { data } = await api.POST("/api/v1/admin/kyc/submissions/{submission_id}/nin/reveal", {
        params: { path: { submission_id: parsed.data.submission_id } },
        body: { purpose: "person_payee_approval" },
      });
      return { done: "NIN read audited.", sensitiveValue: data?.nin };
    }
    if (parsed.data.kind === "account") {
      const { data } = await api.POST(
        "/api/v1/admin/payees/bank-account-versions/{version_id}/reveal",
        {
          params: { path: { version_id: parsed.data.bank_account_version_id } },
          body: { purpose: "person_payee_approval" },
        },
      );
      return {
        done: "Account read audited.",
        sensitiveValue: data
          ? `${data.account_name} · ${data.bank_code} · ${data.account_number}`
          : undefined,
      };
    }
    const { data } = await api.POST("/api/v1/admin/files/{file_id}/download", {
      params: { path: { file_id: parsed.data.file_id } },
      body: {
        purpose: "kyc_review",
        reason: `person_payee_approval:${parsed.data.submission_id}`,
      },
    });
    return { done: "Document read audited.", downloadUrl: data?.url };
  } catch (error) {
    if (error instanceof ApiError) return { error: error.message };
    return { error: "Could not reach the protected evidence service." };
  }
}

const payoutVerificationSchema = z.object({
  bank_account_version_id: z.string().uuid(),
  verification_reference: z.string().min(16).max(512),
});

export async function verifyPersonPayeeAccountAction(
  _previous: PersonPayeeEvidenceState,
  formData: FormData,
): Promise<PersonPayeeEvidenceState> {
  const parsed = payoutVerificationSchema.safeParse({
    bank_account_version_id: String(formData.get("bank_account_version_id") ?? ""),
    verification_reference: String(formData.get("verification_reference") ?? ""),
  });
  if (!parsed.success)
    return { error: "Enter the authorized exact-account verification reference." };
  try {
    await createApiClient(await getSessionToken()).POST(
      "/api/v1/admin/payees/bank-account-versions/{version_id}/payout-verification",
      {
        params: { path: { version_id: parsed.data.bank_account_version_id } },
        body: { verification_reference: parsed.data.verification_reference },
      },
    );
  } catch (error) {
    if (error instanceof ApiError) return { error: error.message };
    return { error: "Could not reach the payout-authority service." };
  }
  revalidatePath("/admin/driver-applications");
  return { done: "Exact account version verified for payout review." };
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
