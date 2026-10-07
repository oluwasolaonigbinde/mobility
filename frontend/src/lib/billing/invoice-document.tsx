import type { components } from "@/lib/api/schema";
import { formatMoneyExact } from "@/lib/format";

type Invoice = components["schemas"]["InvoiceRead"];
type Terms = components["schemas"]["CommercialTermsRead"];

const NOT_RECORDED = "Not yet recorded";

const watDate = new Intl.DateTimeFormat("en-NG", {
  timeZone: "Africa/Lagos",
  day: "numeric",
  month: "long",
  year: "numeric",
});

const calendarDate = new Intl.DateTimeFormat("en-NG", {
  timeZone: "UTC",
  day: "numeric",
  month: "long",
  year: "numeric",
});

const paymentStatusLabel: Record<string, string> = {
  unpaid: "Not yet paid",
  partially_paid: "Part paid",
  paid: "Paid",
};

const paymentClassLabel: Record<string, string> = {
  standard_prepaid: "Paid in full before production",
  approved_corporate_credit: "Approved corporate credit",
};

function text(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

/** An issued instant as a calendar day in Nigeria time (WAT). */
export function formatInvoiceDate(iso: string | null | undefined): string {
  if (!iso) return NOT_RECORDED;
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? NOT_RECORDED : watDate.format(d);
}

/** An instant's calendar day in Nigeria time as YYYY-MM-DD, for date inputs. */
export function watCalendarDate(iso: string | null | undefined): string {
  if (!iso) return "";
  const d = new Date(iso);
  return Number.isNaN(d.getTime())
    ? ""
    : new Intl.DateTimeFormat("en-CA", { timeZone: "Africa/Lagos" }).format(d);
}

/** "1 October 2026 – 31 October 2026 (31 days)" from the accepted quotation's dates. */
export function formatCampaignDuration(scope: Record<string, unknown> | undefined): string {
  const start = text(scope?.campaign_start_date);
  const end = text(scope?.campaign_end_date);
  const startDate = start ? new Date(`${start}T00:00:00Z`) : null;
  const endDate = end ? new Date(`${end}T00:00:00Z`) : null;
  if (!startDate || !endDate || Number.isNaN(startDate.getTime() + endDate.getTime())) {
    return NOT_RECORDED;
  }
  const days = Math.round((endDate.getTime() - startDate.getTime()) / 86_400_000) + 1;
  return `${calendarDate.format(startDate)} – ${calendarDate.format(endDate)} (${days} day${
    days === 1 ? "" : "s"
  })`;
}

/** 0.075 → "7.5 %" */
export function formatVatRate(rate: string): string {
  const percent = Number(rate) * 100;
  return Number.isFinite(percent) ? `${Number(percent.toFixed(4))}%` : "—";
}

function title(invoice: Invoice): { heading: string; note: string | null } {
  if (invoice.status === "draft") {
    return {
      heading: "Draft invoice",
      note: "Not for payment. Terrax Media adds the invoice number and its company details when it issues the invoice.",
    };
  }
  if (invoice.status === "void") return { heading: "Void invoice", note: null };
  if (invoice.issuer_snapshot?.synthetic_test_authority === true) {
    return { heading: "Test invoice", note: "Issued from test data. This is not a tax invoice." };
  }
  return { heading: "Invoice", note: null };
}

function Fact({ label, value }: { label: string; value: string | null }) {
  return (
    <div>
      <dt className="micro text-muted">{label}</dt>
      <dd className={value ? "text-sm" : "text-muted text-sm italic"}>{value ?? NOT_RECORDED}</dd>
    </div>
  );
}

function SignatureLine({ party, role }: { party: string; role: string }) {
  return (
    <div className="space-y-4">
      <p className="text-sm font-medium">{party}</p>
      <p className="micro text-muted">{role}</p>
      {["Name", "Signature", "Date"].map((label) => (
        <p key={label} className="border-edge border-b pb-1 text-sm">
          {label}:
        </p>
      ))}
    </div>
  );
}

export function InvoiceDocument({
  invoice,
  terms,
  campaignName,
}: {
  invoice: Invoice;
  terms: Terms | null;
  campaignName: string;
}) {
  const issuer = invoice.status === "draft" ? null : (invoice.issuer_snapshot ?? {});
  const customer = invoice.customer_snapshot ?? {};
  const address = (customer.address ?? {}) as Record<string, unknown>;
  const { heading, note } = title(invoice);
  const issuerName = text(issuer?.legal_name) ?? "Terrax Media";
  const money = (value: string) => formatMoneyExact(value, invoice.currency);
  const customerAddress = [
    address.line_1,
    address.line_2,
    address.city,
    address.region,
    address.postal_code,
    address.country_code,
  ]
    .map(text)
    .filter(Boolean)
    .join(", ");

  return (
    <article className="border-edge bg-raised mx-auto max-w-4xl space-y-8 rounded-lg border p-8">
      <header className="flex flex-wrap items-start justify-between gap-6">
        <div>
          <h1 className="font-display text-3xl font-semibold">{heading}</h1>
          {note ? <p className="text-amber mt-2 max-w-md text-sm">{note}</p> : null}
        </div>
        <dl className="grid gap-3 text-right">
          <Fact label="Invoice number (serial no.)" value={invoice.invoice_number ?? null} />
          <Fact
            label="Date issued (Nigeria time, WAT)"
            value={invoice.issued_at ? formatInvoiceDate(invoice.issued_at) : null}
          />
        </dl>
      </header>

      <section className="grid gap-8 sm:grid-cols-2">
        <div>
          <h2 className="micro text-muted mb-3">From</h2>
          {issuer ? (
            <dl className="grid gap-2">
              <Fact label="Company" value={text(issuer.legal_name)} />
              <Fact label="Address" value={text(issuer.registered_address)} />
              <Fact label="Phone" value={text(issuer.contact_phone)} />
              <Fact label="Email" value={text(issuer.contact_email)} />
              <Fact label="RC number" value={text(issuer.company_registration_number)} />
              <Fact label="TIN" value={text(issuer.tax_identification_number)} />
            </dl>
          ) : (
            <p className="text-sm">Terrax Media Company Ltd</p>
          )}
        </div>
        <div>
          <h2 className="micro text-muted mb-3">Bill to</h2>
          <dl className="grid gap-2">
            <Fact label="Company" value={text(customer.name)} />
            <Fact label="Client name" value={text(customer.billing_contact_name)} />
            <Fact label="Email" value={text(customer.billing_email)} />
            <Fact label="Phone" value={text(customer.billing_contact_phone)} />
            <Fact label="Address" value={customerAddress || null} />
          </dl>
        </div>
      </section>

      <section>
        <h2 className="micro text-muted mb-3">Campaign</h2>
        <dl className="grid gap-2 sm:grid-cols-3">
          <Fact label="Campaign" value={campaignName} />
          <Fact label="Campaign duration" value={formatCampaignDuration(terms?.production_scope)} />
          <Fact
            label="Payment arrangement"
            value={terms ? (paymentClassLabel[terms.payment_class] ?? terms.payment_class) : null}
          />
        </dl>
      </section>

      <section className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-edge micro text-muted border-b text-left">
              <th className="py-2 pr-3">S/N</th>
              <th className="py-2 pr-3">Services rendered</th>
              <th className="py-2 pr-3 text-right">Quantity</th>
              <th className="py-2 pr-3 text-right">Unit price (before VAT)</th>
              <th className="py-2 text-right">Amount (before VAT)</th>
            </tr>
          </thead>
          <tbody>
            {invoice.line_items.map((line, index) => (
              <tr key={index} className="border-edge/60 border-b">
                <td className="py-2 pr-3">{index + 1}</td>
                <td className="py-2 pr-3">{text(line.description) ?? "—"}</td>
                <td className="py-2 pr-3 text-right">{String(line.quantity ?? 1)}</td>
                <td className="py-2 pr-3 text-right font-mono">
                  {money(String(line.unit_amount ?? line.amount))}
                </td>
                <td className="py-2 text-right font-mono">{money(String(line.amount))}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <dl className="mt-4 ml-auto grid max-w-sm gap-2 text-sm">
          <div className="flex justify-between gap-4">
            <dt>Subtotal (before VAT)</dt>
            <dd className="font-mono">{money(invoice.net_amount)}</dd>
          </div>
          <div className="flex justify-between gap-4">
            <dt>Included VAT</dt>
            <dd className="font-mono">
              VAT {formatVatRate(invoice.tax_rate)} · {money(invoice.tax_amount)}
            </dd>
          </div>
          <div className="border-edge flex justify-between gap-4 border-t pt-2 text-base font-semibold">
            <dt>Invoice total (VAT inclusive)</dt>
            <dd className="font-mono">{money(invoice.gross_amount)}</dd>
          </div>
        </dl>
      </section>

      {invoice.corrections?.length || invoice.status !== "draft" ? (
        <section>
          <h2 className="micro text-muted mb-3">Corrections and payments</h2>
          {invoice.corrections?.length ? (
            <ul className="mb-3 space-y-1 text-sm">
              {invoice.corrections.map((correction) => (
                <li key={correction.id}>
                  {correction.correction_number} ·{" "}
                  {correction.correction_type === "credit_note"
                    ? `Credit note: reduces the invoice by ${money(correction.gross_amount)}`
                    : `Debit note: adds ${money(correction.gross_amount)} to the invoice`}{" "}
                  ({money(correction.net_amount)} + VAT {money(correction.tax_amount)}) ·{" "}
                  {correction.reason}
                </li>
              ))}
            </ul>
          ) : null}
          <dl className="grid gap-2 sm:grid-cols-3">
            <Fact
              label="Amount after corrections (VAT inclusive)"
              value={money(invoice.effective_obligation_amount)}
            />
            <Fact label="Paid so far" value={money(invoice.funded_amount)} />
            <Fact
              label="Payment status"
              value={paymentStatusLabel[invoice.payment_status] ?? invoice.payment_status}
            />
          </dl>
        </section>
      ) : null}

      <section>
        <h2 className="micro text-muted mb-3">Payment details</h2>
        <dl className="grid gap-2 sm:grid-cols-3">
          <Fact label="Bank" value={text(issuer?.bank_name)} />
          <Fact label="Account name" value={text(issuer?.bank_account_name)} />
          <Fact label="Account number" value={text(issuer?.bank_account_number)} />
        </dl>
        {text(issuer?.invoice_wording) ? (
          <p className="text-muted mt-4 text-sm">{text(issuer?.invoice_wording)}</p>
        ) : null}
      </section>

      <section className="grid gap-10 pt-4 sm:grid-cols-2">
        <SignatureLine party="For the client" role={text(customer.name) ?? "Client"} />
        <SignatureLine party={`For ${issuerName}`} role="Chief Executive Officer" />
      </section>
    </article>
  );
}
