import Link from "next/link";
import type { components } from "@/lib/api/schema";
import { formatDate, formatMoney } from "@/lib/format";
import { Panel } from "@/components/ui/panel";
import { StatusChip } from "@/components/ui/status-chip";

type Invoice = components["schemas"]["InvoiceRead"];
type Settlement = components["schemas"]["SettlementRead"];

export function CommercialHistory({
  invoices,
  settlements,
  campaign,
}: {
  invoices: Invoice[];
  settlements: Settlement[];
  campaign?: { id: string; name: string };
}) {
  if (!invoices.length && !settlements.length) return null;

  return (
    <Panel className="mt-6 overflow-hidden">
      <div className="border-edge flex flex-wrap items-start justify-between gap-3 border-b px-6 py-5">
        <div>
          <h3 className="font-display text-lg font-semibold">Invoice and settlement history</h3>
          <p className="micro text-muted mt-1">
            Persisted invoices, corrections, funding and refund lineage
          </p>
        </div>
        {campaign ? (
          <Link
            href={`/advertiser/campaigns/${campaign.id}`}
            className="micro text-amber hover:underline"
          >
            {campaign.name} →
          </Link>
        ) : null}
      </div>

      {invoices.length ? (
        <ul className="divide-edge/60 divide-y">
          {invoices.map((invoice) => (
            <li key={invoice.id} className="px-6 py-5">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <p className="font-mono text-sm">
                    {invoice.invoice_number ?? "Draft — number assigned on issue"}
                  </p>
                  <p className="micro text-muted mt-1">
                    {formatMoney(invoice.gross_amount, invoice.currency)} original ·{" "}
                    {formatMoney(invoice.effective_obligation_amount, invoice.currency)} effective
                  </p>
                </div>
                <div className="text-right">
                  <StatusChip
                    tone={
                      invoice.payment_status === "paid"
                        ? "green"
                        : invoice.payment_status === "partially_paid"
                          ? "amber"
                          : "default"
                    }
                  >
                    {invoice.payment_status.replaceAll("_", " ")}
                  </StatusChip>
                  <p className="micro text-muted mt-1">
                    {formatMoney(invoice.funded_amount, invoice.currency)} funded
                  </p>
                </div>
              </div>

              {invoice.corrections?.length ? (
                <ul className="border-edge mt-4 space-y-3 border-l pl-4">
                  {invoice.corrections.map((correction) => (
                    <li key={correction.id}>
                      <p className="text-sm font-medium">
                        {correction.correction_number} ·{" "}
                        {correction.correction_type.replaceAll("_", " ")}
                      </p>
                      <p className="micro text-muted mt-1">
                        {formatMoney(correction.net_amount, correction.currency)} net +{" "}
                        {formatMoney(correction.tax_amount, correction.currency)} VAT ={" "}
                        {formatMoney(correction.gross_amount, correction.currency)} ·{" "}
                        {correction.reason} · {formatDate(correction.created_at)}
                      </p>
                    </li>
                  ))}
                </ul>
              ) : null}
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-muted px-6 py-5 text-sm">No invoice has been recorded.</p>
      )}

      {settlements.length ? (
        <ul className="divide-edge/60 border-edge divide-y border-t">
          {settlements.map((settlement) => (
            <li
              key={settlement.id}
              className="flex flex-wrap items-start justify-between gap-3 px-6 py-4"
            >
              <div>
                <p className="text-sm font-medium">{settlement.disposition.replaceAll("_", " ")}</p>
                <p className="micro text-muted mt-1">
                  {settlement.reason} · {formatDate(settlement.recorded_at)}
                </p>
                <p className="micro text-muted mt-1">
                  {settlement.settlement_provider} · {settlement.external_reference}
                </p>
              </div>
              <p className="font-mono text-sm">
                {formatMoney(settlement.amount, settlement.currency)}
              </p>
            </li>
          ))}
        </ul>
      ) : null}
    </Panel>
  );
}
