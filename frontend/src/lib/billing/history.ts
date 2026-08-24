import type { components } from "@/lib/api/schema";

type BillingHistoryEntry = components["schemas"]["BillingHistoryEntry"];

export function receiptsAllocatedToTerms(
  history: BillingHistoryEntry[],
  commercialTermsId: string | undefined,
) {
  if (!commercialTermsId) return [];
  return history.filter((entry) =>
    entry.allocations.some((allocation) => allocation.commercial_terms_id === commercialTermsId),
  );
}
