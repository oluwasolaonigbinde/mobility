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

import AdminInvoicePage from "./page";

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

describe("admin invoice page", () => {
  beforeEach(() => vi.clearAllMocks());

  it("shows the invoice for Terrax staff", async () => {
    respond();
    render(await AdminInvoicePage(input()));
    expect(requireRole).toHaveBeenCalledWith("admin");
    expect(get).toHaveBeenCalledWith("/api/v1/admin/campaigns/{campaign_id}/commercial", {
      params: { path: { campaign_id: "campaign-1" } },
    });
    expect(screen.getByText("Invoice invoice-1 for October launch")).toBeVisible();
    expect(screen.getByRole("link", { name: "October launch" })).toHaveAttribute(
      "href",
      "/admin/billing/campaign-1",
    );
  });

  it("is not found for an unknown invoice or campaign and rethrows other failures", async () => {
    respond();
    await expect(AdminInvoicePage(input("other-invoice"))).rejects.toThrow("notFound");
    get.mockRejectedValue(new ApiError(404, { code: "CAMPAIGN_NOT_FOUND", message: "x" }));
    await expect(AdminInvoicePage(input())).rejects.toThrow("notFound");
    get.mockRejectedValue(new ApiError(503, { code: "UNAVAILABLE", message: "x" }));
    await expect(AdminInvoicePage(input())).rejects.toThrow(ApiError);
  });
});
