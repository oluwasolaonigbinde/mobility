import { describe, expect, it, vi } from "vitest";
import type { ApiClient } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";
import { exactCompanyMoney, outstandingInvoices, readCompanyInvoices } from "./company-reads";
type Invoice = components["schemas"]["InvoiceRead"];
function invoice(fields: Partial<Invoice> = {}): Invoice {
  return {
    id: "invoice",
    organization_id: "org",
    campaign_id: "campaign",
    status: "issued",
    currency: "NGN",
    effective_obligation_amount: "100.00",
    funded_amount: "20.00",
    ...fields,
  } as Invoice;
}
describe("company outstanding invoices", () => {
  it("uses corrected obligation and reversed funding snapshots and clamps each invoice", () => {
    expect(
      outstandingInvoices([
        invoice({ effective_obligation_amount: "60.00", funded_amount: "20.00" }),
        invoice({ effective_obligation_amount: "140.00", funded_amount: "10.00" }),
        invoice({ funded_amount: "200.00" }),
        invoice({ currency: "USD", effective_obligation_amount: "5.00", funded_amount: "0.01" }),
        invoice({ status: "draft" }),
        invoice({ status: "void" }),
      ]),
    ).toEqual([
      { currency: "NGN", amount: "170.00" },
      { currency: "USD", amount: "4.99" },
    ]);
  });
  it("retains exact cents above JavaScript safe integer limits", () => {
    const amount = outstandingInvoices([
      invoice({ effective_obligation_amount: "9007199254740993.01", funded_amount: "0.00" }),
    ])[0]!;
    expect(amount.amount).toBe("9007199254740993.01");
    expect(exactCompanyMoney(amount.amount, amount.currency)).toBe("NGN 9,007,199,254,740,993.01");
  });
  it.each(["NaN", "-1.00", "1.001", "1e2", ""])("rejects malformed amount %s", (value) => {
    expect(() => outstandingInvoices([invoice({ effective_obligation_amount: value })])).toThrow();
  });
});
describe("complete company reads", () => {
  const campaign = (id: string) => ({ id, organization_id: "org", status: "active" });
  it("enumerates every campaign page and uses each commercial response once", async () => {
    const get = vi.fn().mockImplementation(async (path, options) => {
      if (path === "/api/v1/admin/campaigns") {
        const offset = options.params.query.offset;
        return { data: { items: [campaign(offset ? "second" : "campaign")], total: 2 } };
      }
      const id = options.params.path.campaign_id;
      return { data: { settlements: [], invoices: [invoice({ id, campaign_id: id })] } };
    });
    const result = await readCompanyInvoices({ GET: get } as unknown as ApiClient, "org");
    expect(result.outstanding).toEqual([{ currency: "NGN", amount: "160.00" }]);
    expect(result.campaigns).toHaveLength(2);
    expect(get).toHaveBeenCalledTimes(4);
    expect(get.mock.calls[1]![1].params.query).toEqual({
      organization_id: "org",
      limit: 100,
      offset: 1,
    });
  });
  it.each([
    "duplicate",
    "foreign invoice",
    "foreign campaign",
    "failed commercial",
    "empty page",
    "changing total",
  ])("rejects %s without returning partial totals", async (failure) => {
    let page = 0;
    const get = vi.fn().mockImplementation(async (path) => {
      if (path === "/api/v1/admin/campaigns") {
        page++;
        if (failure === "empty page") return { data: { items: [], total: 1 } };
        if (failure === "changing total")
          return { data: { items: [campaign(`c${page}`)], total: page === 1 ? 2 : 3 } };
        return {
          data: {
            items: [
              {
                ...campaign("campaign"),
                organization_id: failure === "foreign campaign" ? "other" : "org",
              },
            ],
            total: 1,
          },
        };
      }
      if (failure === "failed commercial") throw new Error("offline");
      return {
        data: {
          settlements: [],
          invoices:
            failure === "duplicate"
              ? [invoice(), invoice()]
              : [invoice({ organization_id: failure === "foreign invoice" ? "other" : "org" })],
        },
      };
    });
    await expect(
      readCompanyInvoices({ GET: get } as unknown as ApiClient, "org"),
    ).rejects.toThrow();
  });
});
