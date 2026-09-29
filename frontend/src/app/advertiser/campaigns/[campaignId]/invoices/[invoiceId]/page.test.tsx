import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "@/lib/api/errors";

const { get, requireRole, notFound } = vi.hoisted(() => ({
  get: vi.fn(),
  requireRole: vi.fn(),
  notFound: vi.fn(() => {
    throw new Error("notFound");
  }),
}));
vi.mock("@/lib/api/client", () => ({ createApiClient: () => ({ GET: get }) }));
vi.mock("@/lib/auth/session", () => ({ getSessionToken: async () => "token" }));
vi.mock("@/lib/auth/current-user", () => ({ requireRole }));
vi.mock("next/navigation", () => ({ notFound }));
vi.mock("@/lib/billing/invoice-document", () => ({
  InvoiceDocument: ({
    invoice,
    campaignName,
  }: {
    invoice: { id: string };
    campaignName: string;
  }) => (
    <p>
      Invoice {invoice.id} for {campaignName}
    </p>
  ),
}));

import AdvertiserInvoicePage from "./page";

const input = (invoiceId = "invoice-1") => ({
  params: Promise.resolve({ campaignId: "campaign-1", invoiceId }),
});

function respond() {
  get.mockImplementation(async (path: string) =>
    path.endsWith("/commercial")
      ? { data: { invoices: [{ id: "invoice-1" }], terms: null } }
      : { data: { id: "campaign-1", name: "October launch" } },
  );
}

describe("advertiser invoice page", () => {
  beforeEach(() => vi.clearAllMocks());

  it("shows the company's own invoice from the campaign's commercial record", async () => {
    respond();
    render(await AdvertiserInvoicePage(input()));
    expect(requireRole).toHaveBeenCalledWith("advertiser");
    expect(get).toHaveBeenCalledWith("/api/v1/advertiser/campaigns/{campaign_id}/commercial", {
      params: { path: { campaign_id: "campaign-1" } },
    });
    expect(screen.getByText("Invoice invoice-1 for October launch")).toBeVisible();
    expect(screen.getByRole("link", { name: "October launch" })).toHaveAttribute(
      "href",
      "/advertiser/campaigns/campaign-1",
    );
  });

  it("is not found for an invoice outside the campaign or a campaign outside the company", async () => {
    respond();
    await expect(AdvertiserInvoicePage(input("other-invoice"))).rejects.toThrow("notFound");
    get.mockRejectedValue(new ApiError(404, { code: "CAMPAIGN_NOT_FOUND", message: "x" }));
    await expect(AdvertiserInvoicePage(input())).rejects.toThrow("notFound");
    get.mockRejectedValue(new ApiError(503, { code: "UNAVAILABLE", message: "x" }));
    await expect(AdvertiserInvoicePage(input())).rejects.toThrow(ApiError);
  });
});
