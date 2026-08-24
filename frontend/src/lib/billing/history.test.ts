import { describe, expect, it } from "vitest";
import type { components } from "@/lib/api/schema";
import { receiptsAllocatedToTerms } from "./history";

type BillingHistoryEntry = components["schemas"]["BillingHistoryEntry"];

function entry(receiptId: string, termsIds: string[]): BillingHistoryEntry {
  return {
    receipt: {
      id: receiptId,
      amount: "100.00",
      currency: "NGN",
      evidence_reference: `evidence-${receiptId}`,
      external_transaction_id: `transaction-${receiptId}`,
      method: "manual_transfer",
      observed_at: "2026-08-24T10:00:00Z",
      organization_id: "00000000-0000-0000-0000-000000000001",
      payer_name: "Advertiser",
      provider: "manual",
    },
    current_status: "confirmed",
    events: [],
    allocations: termsIds.map((commercialTermsId, index) => ({
      id: `00000000-0000-0000-0000-00000000000${index + 2}`,
      receipt_id: receiptId,
      commercial_terms_id: commercialTermsId,
      amount: "100.00",
      currency: "NGN",
      allocated_at: "2026-08-24T10:00:00Z",
    })),
  };
}

describe("receiptsAllocatedToTerms", () => {
  it("keeps receipt actions scoped to the selected campaign terms", () => {
    const targetTerms = "00000000-0000-0000-0000-000000000010";
    const otherTerms = "00000000-0000-0000-0000-000000000020";
    const history = [entry("receipt-target", [targetTerms]), entry("receipt-other", [otherTerms])];

    expect(receiptsAllocatedToTerms(history, targetTerms).map(({ receipt }) => receipt.id)).toEqual(
      ["receipt-target"],
    );
    expect(receiptsAllocatedToTerms(history, undefined)).toEqual([]);
  });
});
