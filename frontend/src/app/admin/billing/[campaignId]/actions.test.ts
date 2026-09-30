import { beforeEach, describe, expect, it, vi } from "vitest";

const { post, redirect, revalidatePath } = vi.hoisted(() => ({
  post: vi.fn(),
  redirect: vi.fn((path: string) => {
    throw new Error(`redirect:${path}`);
  }),
  revalidatePath: vi.fn(),
}));
vi.mock("@/lib/api/client", () => ({ createApiClient: () => ({ POST: post }) }));
vi.mock("@/lib/auth/session", () => ({ getSessionToken: async () => "token" }));
vi.mock("next/navigation", () => ({ redirect }));
vi.mock("next/cache", () => ({ revalidatePath }));

import { recordRevisionAction } from "./actions";

describe("recordRevisionAction", () => {
  beforeEach(() => vi.clearAllMocks());

  it("sends a quantity-priced line and the campaign dates to the quotation API", async () => {
    post.mockResolvedValue({ data: {} });
    const form = new FormData();
    form.set("quote_reference", " Q-1 ");
    form.set("description", "Mobile billboard campaign");
    form.set("quantity", "3");
    form.set("unit_amount", "100000.00");
    form.set("tax_rate", "0.075");
    form.set("currency", "ngn");
    form.set("vehicle_count", "10");
    form.set("campaign_start_date", "2026-10-01");
    form.set("campaign_end_date", "2026-10-31");
    form.set("payment_class", "standard_prepaid");
    form.set("payment_terms", "Pay before printing");

    await expect(recordRevisionAction("campaign-1", "quote-1", form)).rejects.toThrow(
      "redirect:/admin/billing/campaign-1?saved=quotation",
    );
    expect(post).toHaveBeenCalledWith("/api/v1/admin/quote-requests/{quote_request_id}/revisions", {
      params: { path: { quote_request_id: "quote-1" } },
      body: {
        quote_reference: "Q-1",
        currency: "NGN",
        line_items: [
          {
            code: "MEDIA",
            description: "Mobile billboard campaign",
            kind: "media",
            quantity: 3,
            unit_amount: "100000.00",
          },
        ],
        production_scope: {
          vehicle_count: 10,
          campaign_start_date: "2026-10-01",
          campaign_end_date: "2026-10-31",
        },
        payment_class: "standard_prepaid",
        payment_terms: { notes: "Pay before printing" },
        tax_rate: "0.075",
      },
    });
  });
});
