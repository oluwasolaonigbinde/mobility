import type { Metadata } from "next";
import Link from "next/link";
import { createApiClient } from "@/lib/api/client";
import { getSessionToken } from "@/lib/auth/session";
import { formatDate, formatMoney } from "@/lib/format";
import { PageHeader } from "@/components/ui/page-header";
import { Panel } from "@/components/ui/panel";
import { StatusChip } from "@/components/ui/status-chip";
import {
  CommercialHistory,
  InvoicePayForm,
  invoiceStatusLabel,
  invoiceStatusTone,
  isOutstandingInvoice,
} from "@/lib/billing/commercial-history";
import { invoiceAmountLeftToPay, paidTowards } from "@/lib/billing/history";
import { requireRole, isAdvertiserViewer } from "@/lib/auth/current-user";
import {
  loadAdvertiserPageData,
  loadAllAdvertiserPages,
  type UnavailableReason,
} from "@/lib/advertiser/page-data";
import { moneyMinor } from "@/lib/advertiser/budget-display";
import { DataUnavailable } from "@/components/ui/data-unavailable";

export const metadata: Metadata = { title: "Billing" };

const receiptStatusLabel: Record<string, string> = {
  observed: "Recorded – being checked",
  reconciled: "Amount matched – awaiting confirmation",
  confirmed: "Confirmed",
  reversed: "Reversed",
};

function SectionHeading({ id, title, hint }: { id: string; title: string; hint: string }) {
  return (
    <div className="mb-3">
      <h2 id={id} className="font-display text-xl font-semibold">
        {title}
      </h2>
      <p className="text-muted mt-1 text-sm">{hint}</p>
    </div>
  );
}

export default async function AdvertiserBillingPage({
  searchParams,
}: {
  searchParams?: Promise<{ payment?: string; message?: string }>;
}) {
  const paymentResult = (await searchParams) ?? {};
  const me = await requireRole("advertiser");
  const canPay = !isAdvertiserViewer(me);
  const api = createApiClient(await getSessionToken());
  const [historyResult, campaignResult] = await Promise.all([
    loadAdvertiserPageData(() => api.GET("/api/v1/advertiser/billing")),
    loadAllAdvertiserPages((next) =>
      api.GET("/api/v1/advertiser/campaigns", {
        params: { query: { limit: 100, offset: next } },
      }),
    ),
  ]);
  const unavailable = (reason: UnavailableReason = "protocol") => (
    <DataUnavailable title="Billing unavailable" reason={reason} retryHref="/advertiser/billing" />
  );
  if (!historyResult.available) return unavailable(historyResult.reason);
  if (!campaignResult.available) return unavailable(campaignResult.reason);
  const receipts = historyResult.data;
  const campaigns = campaignResult.data;
  const commercialHistory: Array<{
    campaign: (typeof campaigns)[number];
    commercial: import("@/lib/api/schema").components["schemas"]["CampaignCommercialRead"];
  }> = [];
  for (let offset = 0; offset < campaigns.length; offset += 4) {
    const group = await Promise.all(
      campaigns.slice(offset, offset + 4).map(async (campaign) => {
        const result = await loadAdvertiserPageData(() =>
          api.GET("/api/v1/advertiser/campaigns/{campaign_id}/commercial", {
            params: { path: { campaign_id: campaign.id } },
          }),
        );
        return result.available &&
          campaign.status &&
          result.data.invoices.every((invoice) => invoice.campaign_id === campaign.id)
          ? { campaign, commercial: result.data }
          : null;
      }),
    );
    if (group.some((item) => item === null)) return unavailable();
    commercialHistory.push(...group.filter((item) => item !== null));
  }
  // Payments are put towards a campaign's accepted terms; name the campaign behind each.
  const campaignNameByTerms = new Map<string, string>();
  for (const { campaign, commercial } of commercialHistory) {
    if (commercial?.terms) campaignNameByTerms.set(commercial.terms.id, campaign.name);
    for (const invoice of commercial?.invoices ?? []) {
      campaignNameByTerms.set(invoice.commercial_terms_id, campaign.name);
    }
  }
  const payable = commercialHistory.flatMap(({ campaign, commercial }) =>
    campaign.status === "cancelled"
      ? []
      : commercial.invoices.map((invoice) => ({ campaign, invoice })),
  );
  // An unpaid invoice with unreadable amounts is unknown, never "Nothing to pay".
  if (
    payable.some(
      ({ invoice }) =>
        invoice.status === "issued" &&
        invoice.payment_status !== "paid" &&
        (moneyMinor(invoice.effective_obligation_amount) === null ||
          moneyMinor(invoice.funded_amount) === null),
    )
  )
    return unavailable();
  const outstanding = payable.filter(({ invoice }) => isOutstandingInvoice(invoice));
  const withHistory = commercialHistory.filter(
    ({ commercial }) => commercial && (commercial.invoices.length || commercial.settlements.length),
  );

  return (
    <div className="animate-rise mx-auto max-w-6xl">
      <PageHeader
        title="Billing"
        eyebrow="What you owe, what you have paid, and your invoices"
        actions={
          <Link
            href="/advertiser/company"
            className="border-edge bg-raised rounded-lg border px-4 py-2.5 text-sm"
          >
            Billing details
          </Link>
        }
      />
      {paymentResult.payment ? (
        <Panel className="mb-6 px-6 py-4" role="status">
          <p className="text-sm font-semibold">
            {paymentResult.payment === "confirmed"
              ? "Payment confirmed"
              : paymentResult.payment === "failed"
                ? "Paystack did not complete the payment"
                : paymentResult.payment === "pending"
                  ? "Payment confirmation is still pending"
                  : "Online payment could not be opened"}
          </p>
          <p className="text-muted mt-1 text-sm">
            {paymentResult.message ??
              (paymentResult.payment === "confirmed"
                ? "The verified payment is being applied to the invoice."
                : "No payment is treated as complete until Paystack confirms it.")}
          </p>
        </Panel>
      ) : null}

      <section aria-labelledby="to-pay-heading">
        <SectionHeading
          id="to-pay-heading"
          title="To pay"
          hint="Issued invoices that are not fully paid yet"
        />
        {outstanding.some(({ invoice }) => invoice.currency === "NGN") ? (
          <p className="text-muted mb-3 text-sm">
            Card or bank transfer through Paystack. The invoice shows as paid once Paystack confirms
            the payment.
          </p>
        ) : null}
        <Panel className="overflow-hidden">
          {outstanding.length ? (
            <ul className="divide-edge/60 divide-y">
              {outstanding.map(({ campaign, invoice }) => (
                <li key={invoice.id} className="px-6 py-5">
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div>
                      <p className="text-base font-semibold">{campaign.name}</p>
                      <p className="text-muted mt-1 text-xs">Invoice {invoice.invoice_number}</p>
                      <Link
                        href={`/advertiser/campaigns/${invoice.campaign_id}/invoices/${invoice.id}`}
                        className="text-amber mt-1 inline-block text-sm hover:underline"
                      >
                        View invoice
                      </Link>
                    </div>
                    <div className="text-right">
                      <p className="font-display text-xl font-semibold">
                        {formatMoney(invoiceAmountLeftToPay(invoice), invoice.currency)} left to pay
                      </p>
                      <p className="text-muted mt-1 text-sm">
                        of {formatMoney(invoice.effective_obligation_amount, invoice.currency)}
                      </p>
                      <p className="text-muted mt-1 text-sm">
                        {formatMoney(invoice.funded_amount, invoice.currency)} paid so far
                      </p>
                      <StatusChip className="mt-2" tone={invoiceStatusTone(invoice)}>
                        {invoiceStatusLabel(invoice)}
                      </StatusChip>
                    </div>
                  </div>
                  {canPay ? <InvoicePayForm invoice={invoice} showNote={false} /> : null}
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-muted px-6 py-8 text-center text-sm">Nothing to pay right now.</p>
          )}
        </Panel>
      </section>

      <section aria-labelledby="payments-heading" className="mt-10">
        <SectionHeading
          id="payments-heading"
          title="Payments"
          hint="Money recorded from you and the campaign each payment went towards"
        />
        <Panel className="overflow-hidden">
          {receipts.length ? (
            <ul className="divide-edge/60 divide-y">
              {receipts.map((entry) => {
                const lines = paidTowards(entry, campaignNameByTerms);
                return (
                  <li key={entry.receipt.id} className="px-6 py-5">
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <div>
                        <p className="font-mono text-sm">{entry.receipt.external_transaction_id}</p>
                        <p className="text-muted mt-1 text-sm">
                          {entry.receipt.payer_name} · {formatDate(entry.receipt.observed_at)}
                        </p>
                      </div>
                      <div className="text-right">
                        <p className="font-mono text-sm">
                          {formatMoney(entry.receipt.amount, entry.receipt.currency)}
                        </p>
                        <StatusChip
                          tone={
                            entry.current_status === "confirmed"
                              ? "green"
                              : entry.current_status === "reversed"
                                ? "coral"
                                : "amber"
                          }
                        >
                          {receiptStatusLabel[entry.current_status ?? "observed"] ??
                            entry.current_status}
                        </StatusChip>
                      </div>
                    </div>
                    {entry.current_status === "reversed" ? (
                      <p className="text-muted mt-3 text-sm">
                        Reversed – this payment no longer counts towards any campaign.
                      </p>
                    ) : lines.length ? (
                      <ul className="text-muted mt-3 space-y-1 text-sm">
                        {lines.map((line) => (
                          <li key={line.id}>
                            Paid towards: {line.campaign ?? "a campaign's accepted quotation"} ·{" "}
                            {formatMoney(line.amount, line.currency)}
                          </li>
                        ))}
                      </ul>
                    ) : (
                      <p className="text-muted mt-3 text-sm">
                        Not yet matched to a campaign – production cannot start from this payment.
                      </p>
                    )}
                  </li>
                );
              })}
            </ul>
          ) : (
            <p className="text-muted px-6 py-8 text-center text-sm">
              No payments have been recorded yet.
            </p>
          )}
        </Panel>
      </section>

      <section aria-labelledby="invoice-history-heading" className="mt-10">
        <SectionHeading
          id="invoice-history-heading"
          title="Invoice history"
          hint="Every invoice by campaign, with any corrections and refunds"
        />
        {withHistory.length ? (
          withHistory.map(({ campaign, commercial }) =>
            commercial ? (
              <CommercialHistory
                key={campaign.id}
                campaign={{ id: campaign.id, name: campaign.name }}
                invoices={commercial.invoices}
                settlements={commercial.settlements}
                showPayment={false}
              />
            ) : null,
          )
        ) : (
          <Panel>
            <p className="text-muted px-6 py-8 text-center text-sm">No invoices yet.</p>
          </Panel>
        )}
      </section>
    </div>
  );
}
