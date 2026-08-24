import "server-only";

import { env } from "@/lib/env";
import { getSessionToken } from "@/lib/auth/session";

export interface PayoutBatchLine {
  id: string;
  ledger_entry_id: string;
  amount: string;
  currency: string;
  instruction_fingerprint: string;
  idempotency_key: string;
  status: "reserved" | "submitted" | "succeeded" | "failed" | "void";
  provider_transfer_reference?: string | null;
  reconciled_by_user_id?: string | null;
  reconciled_at?: string | null;
}

export interface PayoutBatch {
  id: string;
  status: "draft" | "reserved" | "submitted" | "reconciled" | "completed" | "failed" | "void";
  currency: string;
  total_amount: string;
  instruction_set_fingerprint?: string | null;
  provider_submission_reference?: string | null;
  created_by_user_id: string;
  approved_by_user_id?: string | null;
  created_at: string;
  lines: PayoutBatchLine[];
}

interface ApiErrorBody {
  error?: { message?: string };
}

export async function batchApi<T>(path: string, init?: RequestInit): Promise<T> {
  const token = await getSessionToken();
  const response = await fetch(`${env().API_BASE_URL}/api/v1/admin/payout-batches${path}`, {
    ...init,
    cache: "no-store",
    headers: {
      Authorization: `Bearer ${token}`,
      ...(init?.body ? { "Content-Type": "application/json" } : {}),
      ...init?.headers,
    },
  });
  if (!response.ok) {
    const body = (await response.json().catch(() => ({}))) as ApiErrorBody;
    throw new Error(body.error?.message ?? `Request failed (${response.status})`);
  }
  return (await response.json()) as T;
}
