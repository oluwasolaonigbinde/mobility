import Link from "next/link";
import type { components } from "@/lib/api/schema";
import { formatDate, formatMoney } from "@/lib/format";
import { Panel } from "@/components/ui/panel";
import { StatusChip } from "@/components/ui/status-chip";
import { startInvoicePayment } from "@/app/advertiser/billing/actions";
import { moneyMinor } from "@/lib/advertiser/budget-display";

type Invoice = components["schemas"]["InvoiceRead"];
type Settlement = components["schemas"]["SettlementRead"];

const paymentLabel: Record<string, string> = {
  unpaid: "Not paid",
  partially_paid: "Part paid",
  paid: "Paid",
};

const correctionLabel: Record<string, string> = {
  credit_note: "Credit note",
  debit_note: "Extra charge",
};

const settlementLabel: Record<string, string> = {
  refund_recorded: "Refund",
  credit_settlement_recorded: "Closed without a refund",
};

function words(value: string) {
  return value.replaceAll("_", " ");
}

/** An issued invoice that still has money owing on it. */
export function isOutstandingInvoice(invoice: Invoice) {
  const obligation = moneyMinor(invoice.effective_obligation_amount);
  const funded = moneyMinor(invoice.funded_amount);
  return (
    invoice.status === "issued" &&
    invoice.payment_status !== "paid" &&
    obligation !== null &&
    funded !== null &&
    obligation > funded
  );
}

export function invoiceStatusLabel(invoice: Invoice) {
  if (invoice.status === "draft") return "Draft";
  if (invoice.status === "void") return "Cancelled";
  return paymentLabel[invoice.payment_status] ?? words(invoice.payment_status);
}

export function invoiceStatusTone(invoice: Invoice) {
  if (invoice.status !== "issued") return "default" as const;
  return invoice.payment_status === "paid"
    ? ("green" as const)
    : invoice.payment_status === "partially_paid"
      ? ("amber" as const)
      : ("coral" as const);
}

/** Paystack checkout for an outstanding NGN invoice; other invoices offer no online payment. */
export function InvoicePayForm({
  invoice,
  showNote = true,
}: {
  invoice: Invoice;
  showNote?: boolean;
}) {
  if (!isOutstandingInvoice(invoice) || invoice.currency !== "NGN") return null;
  return (
    <form action={startInvoicePayment} className="mt-4">
      <input type="hidden" name="invoiceId" value={invoice.id} />
      <button
        type="submit"
        className="bg-amber text-ink rounded-lg px-4 py-2 text-sm font-semibold"
      >
        Pay invoice online
      </button>
      {showNote ? (
        <p className="text-muted mt-2 text-sm">
          Card or bank transfer through Paystack. The invoice shows as paid once Paystack confirms
          the payment.
        </p>
      ) : null}
    </form>
  );
}

function InvoiceAmounts({ invoice }: { invoice: Invoice }) {
  const corrected = invoice.effective_obligation_amount !== invoice.gross_amount;
  return (
    <p className="micro text-muted mt-1">
      {formatMoney(invoice.effective_obligation_amount, invoice.currency)} total
      {corrected
        ? ` (was ${formatMoney(invoice.gross_amount, invoice.currency)} before corrections)`
        : ""}{" "}
      · {formatMoney(invoice.funded_amount, invoice.currency)} paid
    </p>
  );
}

/**
 * A campaign's invoices, with corrections and refunds shown as plain lines.
 * On the billing page payment happens in "To pay", so `showPayment` is off there.
 */
export function CommercialHistory({
  invoices,
  settlements,
  campaign,
  showPayment = false,
}: {
  invoices: Invoice[];
  settlements: Settlement[];
  campaign?: { id: string; name: string };
  showPayment?: boolean;
}) {
  if (!invoices.length && !settlements.length) return null;

  return (
    <Panel
      id={campaign ? `campaign-${campaign.id}` : undefined}
      className={campaign ? "mt-4 scroll-mt-24 overflow-hidden" : "mt-6 overflow-hidden"}
    >
      <div className="border-edge flex flex-wrap items-start justify-between gap-3 border-b px-6 py-4">
        {campaign ? (
          <Link
            href={`/advertiser/campaigns/${campaign.id}`}
            className="hover:text-amber font-medium"
          >
            {campaign.name}
          </Link>
        ) : (
          <h3 className="font-display text-lg font-semibold">Invoice history</h3>
        )}
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
                  <InvoiceAmounts invoice={invoice} />
                  <Link
                    href={`/advertiser/billing/${invoice.campaign_id}/invoices/${invoice.id}`}
                    className="micro text-amber mt-1 inline-block hover:underline"
                  >
                    View invoice
                  </Link>
                </div>
                <StatusChip tone={invoiceStatusTone(invoice)}>
                  {invoiceStatusLabel(invoice)}
                </StatusChip>
              </div>

              {invoice.corrections?.length ? (
                <ul className="border-edge mt-4 space-y-2 border-l pl-4">
                  {invoice.corrections.map((correction) => (
                    <li key={correction.id} className="text-sm">
                      {correctionLabel[correction.correction_type] ??
                        words(correction.correction_type)}{" "}
                      {correction.correction_number}:{" "}
                      {formatMoney(correction.gross_amount, correction.currency)} including VAT ·{" "}
                      {correction.reason} · {formatDate(correction.created_at)}
                    </li>
                  ))}
                </ul>
              ) : null}
              {showPayment ? <InvoicePayForm invoice={invoice} /> : null}
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-muted px-6 py-5 text-sm">No invoice yet.</p>
      )}

      {settlements.length ? (
        <ul className="divide-edge/60 border-edge divide-y border-t">
          {settlements.map((settlement) => (
            <li key={settlement.id} className="px-6 py-4 text-sm">
              {settlementLabel[settlement.disposition] ?? words(settlement.disposition)}:{" "}
              {formatMoney(settlement.amount, settlement.currency)} · {settlement.reason} ·{" "}
              {formatDate(settlement.recorded_at)} · reference {settlement.external_reference}
            </li>
          ))}
        </ul>
      ) : null}
    </Panel>
  );
}
