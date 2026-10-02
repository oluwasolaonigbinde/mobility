import Link from "next/link";
import type { components } from "@/lib/api/schema";
import { createApiClient } from "@/lib/api/client";
import { getSessionToken } from "@/lib/auth/session";
import { readCompanyInvoices, type CompanyInvoices } from "../advertisers/company-reads";
import { formatDate, formatMoneyExact } from "@/lib/format";
import { adminStatus } from "@/lib/status/admin";
import { Pagination } from "@/components/ui/pagination";
import { QueueUnavailable } from "../queue-search";
import { moneyHref, type MoneyQuery } from "./navigation";
type Invoice = components["schemas"]["InvoiceRead"];
function cents(value: string) {
  const [whole = "0", fraction = ""] = value.split(".");
  return BigInt(whole) * 100n + BigInt(fraction.padEnd(2, "0"));
}
export function invoiceState(invoice: Invoice) {
  if (invoice.status !== "issued") return invoice.status;
  const due = cents(invoice.effective_obligation_amount),
    funded = cents(invoice.funded_amount);
  return funded >= due ? "paid" : funded > 0n ? "part_paid" : "unpaid";
}
export default async function Invoices({ query }: { query: MoneyQuery }) {
  const api = createApiClient(await getSessionToken());
  const records: CompanyInvoices["invoices"] = [],
    refunds: CompanyInvoices["settlements"] = [];
  try {
    let offset = 0,
      total: number | undefined;
    const seen = new Set<string>(),
      invoiceIds = new Set<string>(),
      settlementIds = new Set<string>();
    do {
      const { data } = await api.GET("/api/v1/admin/advertiser-organizations", {
        params: { query: { limit: 100, offset } },
      });
      if (
        !data ||
        !Number.isSafeInteger(data.total) ||
        data.total < 0 ||
        (total !== undefined && total !== data.total) ||
        (!data.items.length && offset < data.total)
      )
        throw new Error("Incomplete companies");
      total = data.total;
      for (const company of data.items) {
        if (seen.has(company.id)) throw new Error("Duplicate company");
        seen.add(company.id);
        const result = await readCompanyInvoices(api, company.id);
        for (const row of result.invoices) {
          if (invoiceIds.has(row.invoice.id)) throw new Error("Duplicate invoice");
          invoiceIds.add(row.invoice.id);
          records.push(row);
        }
        for (const row of result.settlements) {
          if (settlementIds.has(row.settlement.id)) throw new Error("Duplicate settlement");
          settlementIds.add(row.settlement.id);
          if (row.settlement.disposition === "refund_recorded") refunds.push(row);
        }
      }
      offset += data.items.length;
      if (offset > total) throw new Error("Invalid company count");
    } while (offset < total);
  } catch {
    return <QueueUnavailable />;
  }
  const filters = [
    ["all", "All"],
    ["unpaid", "Unpaid"],
    ["part_paid", "Part-paid"],
    ["paid", "Paid"],
    ["refunds", "Refunds"],
  ];
  const state = filters.some(([key]) => key === query.invoice_status)
    ? query.invoice_status
    : "all";
  const raw = Number(query.invoice_offset ?? 0),
    offset = Number.isFinite(raw) ? Math.max(0, Math.floor(raw)) : 0;
  const matching = records.filter(
    ({ invoice }) => state === "all" || invoiceState(invoice) === state,
  );
  const rows = state === "refunds" ? refunds : matching,
    total = rows.length;
  return (
    <div className="space-y-4">
      <nav aria-label="Invoice filters" className="flex flex-wrap gap-3">
        {filters.map(([key, label]) => (
          <Link
            key={key}
            className="border-edge rounded border px-3 py-2"
            aria-current={state === key ? "page" : undefined}
            href={moneyHref(query, { invoice_status: key, invoice_offset: undefined })}
          >
            {label}
          </Link>
        ))}
      </nav>
      <p>
        {total} matching {state === "refunds" ? "refunds" : "invoices"}
      </p>
      {state === "refunds" ? (
        <ul className="space-y-3">
          {refunds.slice(offset, offset + 25).map(({ settlement, campaign }) => (
            <li className="border-edge rounded border p-4" key={settlement.id}>
              <Link className="underline" href={`/admin/campaigns/${campaign.id}#money`}>
                {campaign.name}
              </Link>
              <p>
                Refund recorded · {formatMoneyExact(settlement.amount, settlement.currency)} ·{" "}
                {formatDate(settlement.recorded_at)}
              </p>
            </li>
          ))}
        </ul>
      ) : (
        <ul className="space-y-3">
          {matching.slice(offset, offset + 25).map(({ invoice, campaign }) => (
            <li className="border-edge rounded border p-4" key={invoice.id}>
              <Link
                className="underline"
                href={`/admin/campaigns/${campaign.id}?drawer=invoice&invoice=${invoice.id}#money`}
              >
                {invoice.invoice_number ?? "Draft invoice"} · {campaign.name}
              </Link>
              <p>
                {campaign.organization.name} · {adminStatus(invoiceState(invoice), "invoice")} ·{" "}
                {formatMoneyExact(invoice.effective_obligation_amount, invoice.currency)}
              </p>
              <p>Recorded funding: {formatMoneyExact(invoice.funded_amount, invoice.currency)}</p>
            </li>
          ))}
        </ul>
      )}
      {!total ? <p>No matching {state === "refunds" ? "refunds" : "invoices"}.</p> : null}
      <Pagination
        total={total}
        limit={25}
        offset={offset}
        hrefFor={(next) => moneyHref(query, { invoice_offset: String(next) })}
      />
    </div>
  );
}
