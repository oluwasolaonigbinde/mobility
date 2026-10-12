import type { components } from "@/lib/api/schema";

type BillingHistoryEntry = components["schemas"]["BillingHistoryEntry"];

/** Display only: the amount still owing on the invoice, including any corrections. */
export function invoiceAmountLeftToPay(
  invoice: Pick<
    components["schemas"]["InvoiceRead"],
    "effective_obligation_amount" | "funded_amount"
  >,
): number {
  return Math.max(0, Number(invoice.effective_obligation_amount) - Number(invoice.funded_amount));
}

export function receiptsAllocatedToTerms(
  history: BillingHistoryEntry[],
  commercialTermsId: string | undefined,
) {
  if (!commercialTermsId) return [];
  return history.filter((entry) =>
    entry.allocations.some((allocation) => allocation.commercial_terms_id === commercialTermsId),
  );
}

/**
 * A payment can be split across campaigns: each allocation puts part of it towards one
 * campaign's accepted terms (and so towards that campaign's invoice). Returns one line per
 * allocation, naming the campaign when it is known.
 */
export function paidTowards(
  entry: BillingHistoryEntry,
  campaignNameByTerms: ReadonlyMap<string, string>,
) {
  return entry.allocations.map((allocation) => ({
    id: allocation.id,
    campaign: campaignNameByTerms.get(allocation.commercial_terms_id),
    amount: allocation.amount,
    currency: allocation.currency,
  }));
}
