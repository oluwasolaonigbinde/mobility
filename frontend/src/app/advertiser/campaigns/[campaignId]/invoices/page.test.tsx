import { render, screen } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import { ApiError } from "@/lib/api/errors";
const mocks = vi.hoisted(() => ({ get: vi.fn(), role: vi.fn() }));
vi.mock("@/lib/api/client", () => ({ createApiClient: () => ({ GET: mocks.get }) }));
vi.mock("@/lib/auth/session", () => ({ getSessionToken: async () => "token" }));
vi.mock("@/lib/auth/current-user", () => ({
  requireRole: mocks.role,
  isAdvertiserViewer: (me: { viewer?: boolean }) => Boolean(me.viewer),
}));
vi.mock("next/navigation", () => ({
  notFound: () => {
    throw new Error("notFound");
  },
  redirect: (path: string) => {
    throw new Error(`redirect:${path}`);
  },
}));
vi.mock("@/app/advertiser/billing/actions", () => ({ startInvoicePayment: vi.fn() }));
import Page from "./page";
const input = { params: Promise.resolve({ campaignId: "one" }) };
const invoice = {
  id: "invoice",
  campaign_id: "one",
  invoice_number: "INV-1",
  status: "issued",
  payment_status: "unpaid",
  currency: "NGN",
  gross_amount: "100.00",
  effective_obligation_amount: "100.00",
  funded_amount: "0.00",
  corrections: [],
};
beforeEach(() => {
  mocks.role.mockResolvedValue({ viewer: false });
  mocks.get.mockReset().mockResolvedValue({ data: { invoices: [], settlements: [] } });
});
it("has a working empty destination", async () => {
  render(await Page(input));
  expect(screen.getByRole("heading", { name: "Invoices" })).toBeInTheDocument();
  expect(screen.getByText("No invoices yet")).toBeInTheDocument();
});
it("does not offer payments to a company viewer", async () => {
  mocks.role.mockResolvedValue({ viewer: true });
  mocks.get.mockResolvedValue({ data: { invoices: [invoice], settlements: [] } });
  render(await Page(input));
  expect(screen.getByText("INV-1")).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "View invoice" })).toHaveAttribute(
    "href",
    "/advertiser/campaigns/one/invoices/invoice",
  );
  expect(screen.queryByRole("button", { name: "Pay invoice online" })).toBeNull();
});
it("retains the real invoice history and existing payment action for an owner", async () => {
  mocks.get.mockResolvedValue({ data: { invoices: [invoice], settlements: [] } });
  render(await Page(input));
  expect(screen.getByText("INV-1")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Pay invoice online" })).toBeEnabled();
  expect(screen.queryByText("No invoices yet")).toBeNull();
});
it("shows unavailable separately from an empty invoice history", async () => {
  mocks.get.mockRejectedValue(new ApiError(503, { code: "DOWN", message: "Private detail" }));
  render(await Page(input));
  expect(screen.getByRole("heading", { name: "Invoices unavailable" })).toBeInTheDocument();
  expect(screen.queryByText("No invoices yet")).toBeNull();
});
it("does not reveal invoices for an inaccessible campaign", async () => {
  mocks.get.mockRejectedValue(new ApiError(404, { code: "MISSING", message: "Missing" }));
  await expect(Page(input)).rejects.toThrow("notFound");
});
