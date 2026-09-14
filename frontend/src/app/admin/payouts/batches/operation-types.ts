import type { components } from "@/lib/api/schema";

export type EligiblePayment = components["schemas"]["EligiblePaymentRead"];
export type BatchSummary = components["schemas"]["PayoutBatchSummaryRead"];
export type BatchDetailLine = components["schemas"]["PayoutOperationLineRead"];
export type BatchDetail = components["schemas"]["PayoutBatchDetailRead"];
export interface Page<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
}

export function outcomeLabel(outcome: string): string {
  return (
    (
      {
        queued: "Queued — not submitted",
        provider_unknown: "Provider outcome unknown",
        succeeded: "Verified paid",
        submitted: "Submitted — awaiting verification",
      } as Record<string, string>
    )[outcome] ?? outcome.replaceAll("_", " ")
  );
}
