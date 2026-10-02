import type { ApiClient } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";

type Campaign = components["schemas"]["AdminCampaignRead"];
type Invoice = components["schemas"]["InvoiceRead"];
export type CompanyInvoices = {
  campaigns: Campaign[];
  invoices: { invoice: Invoice; campaign: Campaign }[];
  settlements: {
    settlement: components["schemas"]["RecordedSettlementRead"];
    campaign: Campaign;
  }[];
  outstanding: { currency: string; amount: string }[];
};

function minorUnits(value: string): bigint {
  if (!/^\d+(?:\.\d{1,2})?$/.test(value)) throw new Error("Invalid invoice amount");
  const [whole = "0", fraction = ""] = value.split(".");
  return BigInt(whole) * 100n + BigInt(fraction.padEnd(2, "0"));
}

export function outstandingInvoices(invoices: Invoice[]) {
  const totals = new Map<string, bigint>();
  for (const invoice of invoices) {
    if (invoice.status !== "issued") continue;
    if (!/^[A-Z]{3}$/.test(invoice.currency)) throw new Error("Invalid invoice currency");
    const obligation = minorUnits(invoice.effective_obligation_amount);
    const funded = minorUnits(invoice.funded_amount);
    const due = obligation > funded ? obligation - funded : 0n;
    totals.set(invoice.currency, (totals.get(invoice.currency) ?? 0n) + due);
  }
  return [...totals]
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([currency, value]) => ({
      currency,
      amount: `${value / 100n}.${String(value % 100n).padStart(2, "0")}`,
    }));
}

export async function readCompanyInvoices(
  api: ApiClient,
  organizationId: string,
): Promise<CompanyInvoices> {
  const campaigns: Campaign[] = [];
  const campaignIds = new Set<string>();
  let total: number | undefined;
  do {
    const { data } = await api.GET("/api/v1/admin/campaigns", {
      params: { query: { organization_id: organizationId, limit: 100, offset: campaigns.length } },
    });
    if (
      !data ||
      !Number.isSafeInteger(data.total) ||
      data.total < 0 ||
      (total !== undefined && total !== data.total) ||
      (!data.items.length && campaigns.length < data.total)
    ) {
      throw new Error("Incomplete company campaigns");
    }
    total = data.total;
    for (const campaign of data.items) {
      if (campaign.organization_id !== organizationId || campaignIds.has(campaign.id)) {
        throw new Error("Invalid company campaign identity");
      }
      campaignIds.add(campaign.id);
      campaigns.push(campaign);
    }
    if (campaigns.length > total) throw new Error("Invalid company campaign count");
  } while (campaigns.length < total);

  const invoices: CompanyInvoices["invoices"] = [];
  const invoiceIds = new Set<string>();
  const settlements: CompanyInvoices["settlements"] = [];
  const settlementIds = new Set<string>();
  // Bound concurrent reads; each complete commercial response is reused for the metrics and rows.
  for (let offset = 0; offset < campaigns.length; offset += 4) {
    const results = await Promise.all(
      campaigns.slice(offset, offset + 4).map(async (campaign) => {
        const { data } = await api.GET("/api/v1/admin/campaigns/{campaign_id}/commercial", {
          params: { path: { campaign_id: campaign.id } },
        });
        if (!data) throw new Error("Incomplete company invoices");
        return { campaign, invoices: data.invoices, settlements: data.settlements };
      }),
    );
    for (const result of results) {
      for (const settlement of result.settlements) {
        if (settlementIds.has(settlement.id) || !/^[A-Z]{3}$/.test(settlement.currency)) {
          throw new Error("Invalid company settlement");
        }
        minorUnits(settlement.amount);
        settlementIds.add(settlement.id);
        settlements.push({ settlement, campaign: result.campaign });
      }
      for (const invoice of result.invoices) {
        if (
          invoice.organization_id !== organizationId ||
          invoice.campaign_id !== result.campaign.id ||
          invoiceIds.has(invoice.id)
        ) {
          throw new Error("Invalid company invoice identity");
        }
        invoiceIds.add(invoice.id);
        invoices.push({ invoice, campaign: result.campaign });
      }
    }
  }
  return {
    campaigns,
    invoices,
    settlements,
    outstanding: outstandingInvoices(invoices.map(({ invoice }) => invoice)),
  };
}

export function exactCompanyMoney(amount: string, currency: string) {
  const [whole = "0", fraction] = amount.split(".");
  return `${currency} ${BigInt(whole).toLocaleString("en-NG")}.${fraction}`;
}
