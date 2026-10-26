import { adminValueFailure } from "@/lib/api/admin-read";
import { randomUUID } from "node:crypto";
import Link from "next/link";
import { createApiClient } from "@/lib/api/client";
import { getSessionToken } from "@/lib/auth/session";
import { requireRole } from "@/lib/auth/current-user";
import { receiptsAllocatedToTerms } from "@/lib/billing/history";
import { watCalendarDate } from "@/lib/billing/invoice-document";
import { formatDate, formatMoney } from "@/lib/format";
import { Button } from "@/components/ui/button";
import { Field } from "@/components/ui/field";
import { PageHeader } from "@/components/ui/page-header";
import { Panel } from "@/components/ui/panel";
import { adminStatus } from "@/lib/status/admin";
import { StatusChip } from "@/components/ui/status-chip";
import { QueueUnavailable } from "../../queue-search";
import { readCampaign, readCampaignCommercial } from "../../entity-reads";
import { recordRevisionAction } from "./actions";
import {
  createInvoiceAction,
  issueInvoiceAction,
  recordFinancialAuthorityAction,
  recordInvoiceCorrectionAction,
  recordManualTransferAction,
  recordProductionStartAction,
  recordRefundAction,
  reverseReceiptAction,
} from "./actions";

export default async function AdminCampaignBillingPage({
  params,
  searchParams,
  embedded = false,
}: {
  embedded?: boolean;
  params: Promise<{ campaignId: string }>;
  searchParams: Promise<{ error?: string; saved?: string }>;
}) {
  const { campaignId } = await params;
  const me = await requireRole("admin");
  const notice = await searchParams;
  const api = createApiClient(await getSessionToken());
  let campaign, commercial, history;
  try {
    [{ data: campaign }, { data: commercial }] = await Promise.all([
      readCampaign(campaignId),
      readCampaignCommercial(campaignId),
    ]);
    if (campaign) {
      ({ data: history } = await api.GET("/api/v1/admin/billing", {
        params: { query: { organization_id: campaign.organization.id } },
      }));
    }
  } catch (error) {
    adminValueFailure(error);
    return <QueueUnavailable />;
  }
  if (!campaign || !commercial || !history) return <QueueUnavailable />;
  const latest = commercial.revisions.at(-1);
  const quoteLines = latest?.line_items.length
    ? [...latest.line_items]
    : [{ code: "MEDIA", kind: "media", description: "", quantity: 1, unit_amount: "" }];
  if (!quoteLines.some((line) => line.kind === "production"))
    quoteLines.push({
      code: "PRINT",
      kind: "production",
      description: "Printing and fitting",
      quantity: 1,
      unit_amount: "0",
    });
  const invoice = commercial.invoices.at(-1);
  const termsId = commercial.terms?.id;
  const receiptEntries = receiptsAllocatedToTerms(history ?? [], termsId);
  const revisionAction = commercial.quote_request
    ? recordRevisionAction.bind(null, campaignId, commercial.quote_request.id)
    : undefined;

  return (
    <div className="animate-rise mx-auto max-w-6xl">
      {!embedded ? (
        <>
          <nav className="micro text-muted mb-4">
            <Link href="/admin/campaigns">Campaigns</Link> / {campaign.name}
          </nav>
          <PageHeader
            title={campaign.name}
            eyebrow={campaign.organization.name}
            actions={
              <Link
                href={`/admin/advertisers/${campaign.organization.id}#details`}
                className="border-edge bg-raised rounded-lg border px-4 py-2.5 text-sm"
              >
                Edit company details
              </Link>
            }
          />
        </>
      ) : null}
      <Link
        className="mb-4 inline-block underline"
        href={`/admin/campaigns/${campaignId}?drawer=closeout#money`}
      >
        Review settlement and payout position
      </Link>
      {notice.error ? <p className="text-coral mb-4 text-sm">{notice.error}</p> : null}
      <div className="grid gap-6 lg:grid-cols-2">
        <Panel className="p-6">
          <div className="mb-4 flex items-center justify-between gap-3">
            <h2 className="font-display text-xl font-semibold">Quotation</h2>
            <StatusChip tone={commercial.terms ? "green" : latest ? "amber" : "default"}>
              {commercial.terms
                ? "Accepted"
                : latest
                  ? "Sent"
                  : commercial.quote_request
                    ? "Requested"
                    : "No request"}
            </StatusChip>
          </div>
          {latest ? (
            <dl className="space-y-3 text-sm">
              <div>
                <dt className="micro text-muted">Reference</dt>
                <dd>
                  {latest.quote_reference} · version {latest.revision_number}
                </dd>
              </div>
              <div>
                <dt className="micro text-muted">Net</dt>
                <dd className="font-mono">{formatMoney(latest.net_amount, latest.currency)}</dd>
              </div>
              <div>
                <dt className="micro text-muted">VAT</dt>
                <dd className="font-mono">{formatMoney(latest.tax_amount, latest.currency)}</dd>
              </div>
              <div>
                <dt className="micro text-muted">Gross</dt>
                <dd className="font-mono">{formatMoney(latest.gross_amount, latest.currency)}</dd>
              </div>
              <div>
                <dt className="micro text-muted">Payment</dt>
                <dd>{adminStatus(latest.payment_class, "payment_class")}</dd>
              </div>
            </dl>
          ) : null}
          {!commercial.terms && commercial.quote_request && revisionAction ? (
            <form action={revisionAction} className="mt-4 grid gap-4">
              <input
                type="hidden"
                name="previous_production_scope"
                value={JSON.stringify(latest?.production_scope ?? {})}
              />
              <input
                type="hidden"
                name="previous_payment_terms"
                value={JSON.stringify(latest?.payment_terms ?? {})}
              />
              <Field
                name="quote_reference"
                label="Quote reference"
                defaultValue={latest?.quote_reference}
                required
              />
              {quoteLines.map((line, index) => (
                <div key={index} className="grid gap-3">
                  <input type="hidden" name="line_code" value={String(line.code)} />
                  <input type="hidden" name="line_kind" value={String(line.kind)} />
                  <input
                    type="hidden"
                    name="line_metadata"
                    value={JSON.stringify(line.metadata ?? {})}
                  />
                  <Field
                    name="description"
                    label={
                      line.kind === "production" ? "Production description" : "Services rendered"
                    }
                    defaultValue={String(line.description ?? "")}
                    required
                  />
                  <div className="grid grid-cols-2 gap-4">
                    {line.kind === "production" ? (
                      <input type="hidden" name="quantity" value="1" />
                    ) : (
                      <Field
                        name="quantity"
                        label="Quantity (number of advert campaigns)"
                        type="number"
                        min={1}
                        defaultValue={String(line.quantity ?? 1)}
                        required
                      />
                    )}
                    <Field
                      name="unit_amount"
                      label={
                        line.kind === "production"
                          ? "Production amount before VAT (optional)"
                          : "Unit price before VAT"
                      }
                      inputMode="decimal"
                      defaultValue={String(
                        line.kind === "production"
                          ? (line.amount ?? line.unit_amount ?? "0")
                          : (line.unit_amount ?? line.amount ?? ""),
                      )}
                      required={line.kind !== "production"}
                    />
                  </div>
                </div>
              ))}
              <div className="grid grid-cols-2 gap-4">
                <Field
                  name="tax_rate"
                  label="VAT rate (decimal, 0.075 = 7.5 %)"
                  inputMode="decimal"
                  defaultValue={latest?.tax_rate ?? "0.075"}
                  required
                />
                <Field
                  name="currency"
                  label="Currency"
                  defaultValue={latest?.currency ?? campaign.currency}
                  required
                />
              </div>
              <div className="grid grid-cols-3 gap-4">
                <Field
                  name="campaign_start_date"
                  label="Campaign start date"
                  type="date"
                  defaultValue={String(
                    latest?.production_scope.campaign_start_date ??
                      watCalendarDate(campaign.start_at),
                  )}
                  required
                />
                <Field
                  name="campaign_end_date"
                  label="Campaign end date"
                  type="date"
                  defaultValue={String(
                    latest?.production_scope.campaign_end_date ?? watCalendarDate(campaign.end_at),
                  )}
                  required
                />
                <Field
                  name="vehicle_count"
                  label="Vehicle count"
                  type="number"
                  min={1}
                  defaultValue={
                    latest ? String(latest.production_scope.vehicle_count ?? "") : undefined
                  }
                  required
                />
              </div>
              <label className="micro text-muted">
                Payment arrangement
                <select
                  name="payment_class"
                  defaultValue={latest?.payment_class}
                  className="border-edge bg-raised mt-1.5 h-11 w-full rounded-lg border px-3.5 text-sm"
                >
                  <option value="standard_prepaid">Pay before production</option>
                  <option value="approved_corporate_credit">Approved company credit</option>
                </select>
              </label>
              <Field
                name="payment_terms"
                label="Payment terms and supporting notes"
                defaultValue={latest ? String(latest.payment_terms.notes ?? "") : undefined}
                required
              />
              <Button type="submit">Save quotation version</Button>
            </form>
          ) : !latest && !commercial.terms ? (
            <p className="text-muted text-sm">The advertiser has not requested a quotation.</p>
          ) : null}
        </Panel>
        <Panel className="p-6">
          <h2 className="font-display text-xl font-semibold">Accepted terms</h2>
          {commercial.terms ? (
            <dl className="mt-4 space-y-3 text-sm">
              <div>
                <dt className="micro text-muted">Accepted total</dt>
                <dd className="font-mono">
                  {formatMoney(commercial.terms.gross_amount, commercial.terms.currency)}
                </dd>
              </div>
              <div>
                <dt className="micro text-muted">Acceptance</dt>
                <dd>{adminStatus(commercial.terms.acceptance_method, "acceptance_method")}</dd>
              </div>
              <div>
                <dt className="micro text-muted">Production wait</dt>
                <dd>{commercial.terms.standard_production_wait_hours} hours</dd>
              </div>
            </dl>
          ) : (
            <p className="text-muted mt-4 text-sm">No accepted terms yet.</p>
          )}
        </Panel>
      </div>

      {commercial.terms ? (
        <div className="mt-6 grid gap-6 lg:grid-cols-2">
          <Panel className="p-6">
            <h2 className="font-display text-xl font-semibold">Manual bank transfer</h2>
            <p className="micro text-muted mt-1 mb-4">
              The transfer must match the expected payment before it can be confirmed and assigned
              to this campaign.
            </p>
            <form
              action={recordManualTransferAction.bind(
                null,
                campaignId,
                campaign.organization.id,
                commercial.terms.id,
              )}
              className="grid gap-4"
            >
              <Field name="external_transaction_id" label="Bank transaction reference" required />
              <div className="grid grid-cols-2 gap-4">
                <Field name="observed_amount" label="Observed amount" required />
                <Field
                  name="expected_amount"
                  label="Expected amount"
                  defaultValue={commercial.terms.gross_amount}
                  required
                />
              </div>
              <div className="grid grid-cols-2 gap-4">
                <Field name="allocation_amount" label="Allocation amount (optional)" />
                <Field
                  name="currency"
                  label="Currency"
                  defaultValue={commercial.terms.currency}
                  required
                />
              </div>
              <Field name="payer_name" label="Payer name" required />
              <Field name="evidence_reference" label="Evidence reference" required />
              <Button type="submit">Check and record transfer</Button>
            </form>
          </Panel>

          <Panel className="p-6">
            <div className="flex items-start justify-between gap-3">
              <div>
                <h2 className="font-display text-xl font-semibold">Invoice</h2>
                <p className="micro text-muted mt-1">
                  Saved invoice amounts with VAT shown separately
                </p>
              </div>
              <StatusChip
                tone={invoice?.status === "issued" ? "green" : invoice ? "amber" : "default"}
              >
                {invoice ? adminStatus(invoice.status) : "Not created"}
              </StatusChip>
            </div>
            {invoice ? (
              <div className="mt-4">
                <p className="font-mono text-sm">
                  {invoice.invoice_number ?? "Draft — no number assigned"}
                </p>
                <p className="micro text-muted mt-1">
                  {formatMoney(invoice.net_amount, invoice.currency)} net ·{" "}
                  {formatMoney(invoice.tax_amount, invoice.currency)} VAT ·{" "}
                  {formatMoney(invoice.gross_amount, invoice.currency)} gross
                </p>
                <Link
                  className="micro text-amber mt-1 inline-block hover:underline"
                  href={`/admin/campaigns/${campaignId}?drawer=invoice&invoice=${invoice.id}#money`}
                >
                  View invoice
                </Link>
                <div className="border-edge mt-4 grid gap-3 rounded-lg border p-4 sm:grid-cols-3">
                  <div>
                    <p className="micro text-muted">Current amount due</p>
                    <p className="mt-1 font-mono text-sm">
                      {formatMoney(invoice.effective_obligation_amount, invoice.currency)}
                    </p>
                  </div>
                  <div>
                    <p className="micro text-muted">Funded</p>
                    <p className="mt-1 font-mono text-sm">
                      {formatMoney(invoice.funded_amount, invoice.currency)}
                    </p>
                  </div>
                  <div>
                    <p className="micro text-muted">Payment status</p>
                    <p className="mt-1 text-sm">{adminStatus(invoice.payment_status)}</p>
                  </div>
                </div>
                {invoice.corrections?.length ? (
                  <ul className="border-edge mt-4 space-y-3 border-l pl-4">
                    {invoice.corrections.map((correction) => (
                      <li key={correction.id}>
                        <p className="text-sm font-medium">
                          {correction.correction_number} ·{" "}
                          {adminStatus(correction.correction_type, "correction_type")}
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
                {invoice.status === "issued" ? (
                  <form
                    action={recordInvoiceCorrectionAction.bind(null, campaignId, invoice.id)}
                    className="border-edge mt-5 grid gap-3 border-t pt-5"
                  >
                    <input type="hidden" name="correction_reference" value={randomUUID()} />
                    <label className="micro text-muted">
                      Correction type
                      <select
                        name="correction_type"
                        className="border-edge bg-raised mt-1.5 h-11 w-full rounded-lg border px-3.5 text-sm"
                      >
                        <option value="credit_note">Credit note</option>
                        <option value="debit_note">Debit note</option>
                      </select>
                    </label>
                    <div className="grid grid-cols-2 gap-3">
                      <Field name="net_amount" label="Net" required />
                      <Field name="tax_amount" label="VAT" required />
                    </div>
                    <Field name="reason" label="Correction reason" required />
                    <Button type="submit" variant="ghost">
                      Record correction
                    </Button>
                  </form>
                ) : invoice.status === "draft" && commercial.issuing_available ? (
                  <form
                    action={issueInvoiceAction.bind(null, campaignId, invoice.id)}
                    className="mt-4"
                  >
                    <Button type="submit">Issue invoice</Button>
                  </form>
                ) : invoice.status === "draft" ? (
                  <p className="text-amber mt-4 text-sm">
                    Invoices can&apos;t be issued yet: Terrax&apos;s bank details and the
                    accountant&apos;s check are still needed.
                  </p>
                ) : null}
              </div>
            ) : (
              <form
                action={createInvoiceAction.bind(null, campaignId, commercial.terms.id)}
                className="mt-5"
              >
                <Button type="submit">Create invoice draft</Button>
              </form>
            )}
          </Panel>
        </div>
      ) : null}

      {receiptEntries.length && termsId ? (
        <div className="mt-6 space-y-6">
          {receiptEntries.map((receiptEntry) => (
            <Panel key={receiptEntry.receipt.id} className="p-6">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <h2 className="font-display text-xl font-semibold">
                    Receipt reversal &amp; settlement
                  </h2>
                  <p className="micro text-muted mt-1">
                    {receiptEntry.receipt.external_transaction_id} ·{" "}
                    {formatMoney(receiptEntry.receipt.amount, receiptEntry.receipt.currency)}
                  </p>
                </div>
                <StatusChip tone={receiptEntry.current_status === "reversed" ? "coral" : "green"}>
                  {receiptEntry.current_status ?? "observed"}
                </StatusChip>
              </div>
              {receiptEntry.current_status !== "reversed" ? (
                <form
                  action={reverseReceiptAction.bind(null, campaignId, receiptEntry.receipt.id)}
                  className="mt-5 flex flex-col gap-3 sm:flex-row"
                >
                  <input
                    name="reason"
                    required
                    placeholder="Reversal reason"
                    className="border-edge bg-raised h-11 flex-1 rounded-lg border px-3.5 text-sm"
                  />
                  <Button type="submit" variant="danger">
                    Record reversal
                  </Button>
                </form>
              ) : (
                <form
                  action={recordRefundAction.bind(
                    null,
                    campaignId,
                    termsId,
                    receiptEntry.receipt.id,
                  )}
                  className="mt-5 grid gap-3 md:grid-cols-2"
                >
                  <Field name="amount" label="Refund amount" required />
                  <Field name="settlement_provider" label="Settlement provider" required />
                  <Field name="external_reference" label="External settlement reference" required />
                  <Field name="reason" label="Settlement reason" required />
                  <div className="md:col-span-2">
                    <Button type="submit">Record refund settlement</Button>
                  </div>
                </form>
              )}
            </Panel>
          ))}
        </div>
      ) : null}

      {commercial.settlements.length ? (
        <Panel className="mt-6 overflow-hidden">
          <div className="px-6 py-5">
            <h2 className="font-display text-xl font-semibold">Settlement history</h2>
            <p className="micro text-muted mt-1">
              Recorded refund and credit settlements for this campaign
            </p>
          </div>
          <ul className="divide-edge/60 border-edge divide-y border-t">
            {commercial.settlements.map((settlement) => (
              <li
                key={settlement.id}
                className="flex flex-wrap items-start justify-between gap-3 px-6 py-4"
              >
                <div>
                  <p className="text-sm font-medium">
                    {adminStatus(settlement.disposition, "settlement")}
                  </p>
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
        </Panel>
      ) : null}

      {commercial.terms ? (
        <div className="mt-6 grid gap-6 lg:grid-cols-2">
          <Panel className="p-6">
            <div className="flex items-start justify-between gap-3">
              <div>
                <h2 className="font-display text-xl font-semibold">
                  Funding and permission to start production
                </h2>
                <p className="micro text-muted mt-1">
                  The amount owed to drivers is separate from the advertiser price.
                </p>
              </div>
              <StatusChip
                tone={
                  commercial.production_start
                    ? "green"
                    : commercial.financial_authority
                      ? "amber"
                      : "default"
                }
              >
                {commercial.production_start
                  ? "Production started"
                  : commercial.financial_authority
                    ? "Funded — start pending"
                    : "Pending funding"}
              </StatusChip>
            </div>
            {commercial.financial_authority ? (
              <p className="mt-5 text-sm">
                Current maximum amount owed to drivers:{" "}
                {formatMoney(
                  commercial.financial_authority.max_driver_liability,
                  commercial.terms.currency,
                )}
              </p>
            ) : null}
            <form
              action={recordFinancialAuthorityAction.bind(
                null,
                campaignId,
                commercial.terms.payment_class as "standard_prepaid" | "approved_corporate_credit",
                me.user.id,
              )}
              className="mt-5 grid gap-4"
            >
              <Field name="max_driver_liability" label="Maximum amount owed to drivers" required />
              {commercial.terms.payment_class === "approved_corporate_credit" ? (
                <>
                  <Field name="credit_limit" label="Approved credit limit" required />
                  <Field name="due_at" label="Credit due at" type="datetime-local" required />
                  <Field name="credit_terms" label="Approved credit terms" required />
                </>
              ) : null}
              <Field name="reason" label="Supporting record and reason" required />
              <Button type="submit">Record funding approval</Button>
            </form>
            {commercial.financial_authority && !commercial.production_start ? (
              <div className="mt-5">
                <p className="text-muted mb-3 text-sm">
                  Pay-before-production campaigns start after the full 24-hour waiting period,
                  unless the advertiser’s recorded permission for an earlier start is supplied. The
                  server rechecks the boundary.
                </p>
                <form
                  action={recordProductionStartAction.bind(
                    null,
                    campaignId,
                    commercial.waiver?.id ?? null,
                  )}
                >
                  <Button type="submit">Record production start</Button>
                </form>
              </div>
            ) : commercial.production_start ? (
              <p className="mt-5 text-sm">
                Basis:{" "}
                {adminStatus(commercial.production_start.authority_basis, "production_authority")}
              </p>
            ) : null}
          </Panel>
        </div>
      ) : null}
    </div>
  );
}
