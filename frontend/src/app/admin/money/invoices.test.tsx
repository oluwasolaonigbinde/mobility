import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
const mocks = vi.hoisted(() => ({ get: vi.fn(), read: vi.fn() }));
vi.mock("@/lib/api/client", () => ({ createApiClient: () => ({ GET: mocks.get }) }));
vi.mock("@/lib/auth/session", () => ({ getSessionToken: vi.fn(async () => "token") }));
vi.mock("../advertisers/company-reads", () => ({ readCompanyInvoices: mocks.read }));
import Invoices, { invoiceState } from "./invoices";
const campaign = { id: "campaign", name: "City campaign", organization: { name: "Named company" } };
const invoice = (id: string, funded = "0.00", amount = "100.00") => ({
  id,
  status: "issued",
  invoice_number: id,
  currency: "NGN",
  effective_obligation_amount: amount,
  funded_amount: funded,
});
describe("Money invoices", () => {
  beforeEach(() => {
    vi.resetAllMocks();
    mocks.get.mockResolvedValue({ data: { items: [{ id: "company" }], total: 1 } });
    mocks.read.mockResolvedValue({ invoices: [], settlements: [] });
  });
  it("uses exact decimal funding to distinguish unpaid, part paid, and paid", () => {
    expect(invoiceState(invoice("a", "9007199254740993.00", "9007199254740993.01") as never)).toBe(
      "part_paid",
    );
    expect(invoiceState(invoice("b") as never)).toBe("unpaid");
    expect(invoiceState(invoice("c", "100.00") as never)).toBe("paid");
  });
  it("enumerates all company pages before filtering and pages without dropping query state", async () => {
    mocks.get
      .mockResolvedValueOnce({ data: { items: [{ id: "a" }], total: 2 } })
      .mockResolvedValueOnce({ data: { items: [{ id: "b" }], total: 2 } });
    mocks.read
      .mockResolvedValueOnce({
        invoices: [{ invoice: invoice("unpaid"), campaign }],
        settlements: [],
      })
      .mockResolvedValueOnce({
        invoices: Array.from({ length: 26 }, (_, i) => ({
          invoice: invoice("part-" + i, "50.00"),
          campaign,
        })),
        settlements: [],
      });
    render(await Invoices({ query: { tab: "invoices", invoice_status: "part_paid", q: "kept" } }));
    expect(mocks.get).toHaveBeenLastCalledWith("/api/v1/admin/advertiser-organizations", {
      params: { query: { limit: 100, offset: 1 } },
    });
    expect(screen.getByText("26 matching invoices")).toBeVisible();
    expect(screen.queryByText("unpaid · City campaign")).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Next →" })).toHaveAttribute(
      "href",
      "/admin/money?tab=invoices&invoice_status=part_paid&q=kept&invoice_offset=25",
    );
    expect(screen.getByRole("link", { name: "part-0 · City campaign" })).toHaveAttribute(
      "href",
      "/admin/campaigns/campaign?drawer=invoice&invoice=part-0#money",
    );
  });
  it.each(["failed", "incomplete", "duplicate", "changed"])(
    "shows one section failure for %s complete read",
    async (kind) => {
      if (kind === "failed") mocks.read.mockRejectedValue(new Error("down"));
      if (kind === "incomplete") mocks.get.mockResolvedValue({ data: { items: [], total: 2 } });
      if (kind === "duplicate")
        mocks.get.mockResolvedValue({ data: { items: [{ id: "a" }, { id: "a" }], total: 2 } });
      if (kind === "changed")
        mocks.get
          .mockResolvedValueOnce({ data: { items: [{ id: "a" }], total: 2 } })
          .mockResolvedValueOnce({ data: { items: [{ id: "b" }], total: 3 } });
      render(await Invoices({ query: {} }));
      expect(screen.getAllByRole("alert")).toHaveLength(1);
      expect(screen.queryByText(/matching invoices/)).not.toBeInTheDocument();
    },
  );
  it("lists only recorded refund settlements without inventing an invoice association", async () => {
    mocks.read.mockResolvedValue({
      invoices: [{ invoice: invoice("unpaid"), campaign }],
      settlements: [
        {
          campaign,
          settlement: {
            id: "refund",
            disposition: "refund_recorded",
            amount: "12.34",
            currency: "NGN",
            recorded_at: "2026-10-01T12:00:00Z",
          },
        },
        {
          campaign,
          settlement: {
            id: "credit",
            disposition: "credit_recorded",
            amount: "10.00",
            currency: "NGN",
          },
        },
      ],
    });
    render(await Invoices({ query: { tab: "invoices", invoice_status: "refunds" } }));
    expect(screen.getByText("1 matching refunds")).toBeVisible();
    expect(screen.getByText(/Refund recorded · ₦12.34/)).toBeVisible();
    expect(screen.getByRole("link", { name: "City campaign" })).toHaveAttribute(
      "href",
      "/admin/campaigns/campaign#money",
    );
  });
  it("rejects an invoice repeated across separate company snapshots", async () => {
    mocks.get.mockResolvedValue({ data: { items: [{ id: "a" }, { id: "b" }], total: 2 } });
    mocks.read.mockResolvedValue({
      invoices: [{ invoice: invoice("duplicate"), campaign }],
      settlements: [],
    });
    render(await Invoices({ query: {} }));
    expect(screen.getAllByRole("alert")).toHaveLength(1);
    expect(screen.queryByText(/matching invoices/)).not.toBeInTheDocument();
  });
});
