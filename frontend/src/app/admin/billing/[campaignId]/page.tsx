import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { createApiClient } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import { getSessionToken } from "@/lib/auth/session";
import { requireRole } from "@/lib/auth/current-user";
import { receiptsAllocatedToTerms } from "@/lib/billing/history";
import { formatDate, formatMoney } from "@/lib/format";
import { Button } from "@/components/ui/button";
import { Field } from "@/components/ui/field";
import { PageHeader } from "@/components/ui/page-header";
import { Panel } from "@/components/ui/panel";
import { StatusChip } from "@/components/ui/status-chip";
import { recordRevisionAction } from "./actions";
import {
  createInvoiceAction,
  recordBudgetBlockedStateAction,
  recordFinancialAuthorityAction,
  recordInvoiceCorrectionAction,
  recordManualTransferAction,
  recordProductionStartAction,
  recordRefundAction,
  reverseReceiptAction,
} from "./actions";

export const metadata: Metadata = { title: "Campaign billing" };

export default async function AdminCampaignBillingPage({
  params,
  searchParams,
}: {
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
      api.GET("/api/v1/admin/campaigns/{campaign_id}", {
        params: { path: { campaign_id: campaignId } },
      }),
      api.GET("/api/v1/admin/campaigns/{campaign_id}/commercial", {
        params: { path: { campaign_id: campaignId } },
      }),
    ]);
    if (campaign) {
      ({ data: history } = await api.GET("/api/v1/admin/billing", {
        params: { query: { organization_id: campaign.organization.id } },
      }));
    }
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) notFound();
    throw error;
  }
  if (!campaign || !commercial) notFound();
  const latest = commercial.revisions.at(-1);
  const invoice = commercial.invoices.at(-1);
  const termsId = commercial.terms?.id;
  const receiptEntries = receiptsAllocatedToTerms(history ?? [], termsId);
  const revisionAction = commercial.quote_request
    ? recordRevisionAction.bind(null, campaignId, commercial.quote_request.id)
    : undefined;

  return (
    <div className="animate-rise mx-auto max-w-6xl">
      <nav className="micro text-muted mb-4">
        <Link href="/admin/billing">Billing</Link> / {campaign.name}
      </nav>
      <PageHeader
        title={campaign.name}
        eyebrow={campaign.organization.name}
        actions={
          <Link
            href={`/admin/advertisers/${campaign.organization.id}/company?campaign=${campaignId}`}
            className="border-edge bg-raised rounded-lg border px-4 py-2.5 text-sm"
          >
            Edit company details
          </Link>
        }
      />
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
                  {latest.quote_reference} · revision {latest.revision_number}
                </dd>
              </div>
              <div>
                <dt className="micro text-muted">Gross</dt>
                <dd className="font-mono">{formatMoney(latest.gross_amount, latest.currency)}</dd>
              </div>
              <div>
                <dt className="micro text-muted">Payment</dt>
                <dd>{latest.payment_class.replaceAll("_", " ")}</dd>
              </div>
            </dl>
          ) : commercial.quote_request && revisionAction ? (
            <form action={revisionAction} className="grid gap-4">
              <Field name="quote_reference" label="Quote reference" required />
              <Field name="description" label="Line-item description" required />
              <div className="grid grid-cols-2 gap-4">
                <Field name="amount" label="Net amount" inputMode="decimal" required />
                <Field name="tax_rate" label="Tax rate (decimal)" inputMode="decimal" required />
              </div>
              <div className="grid grid-cols-2 gap-4">
                <Field name="currency" label="Currency" defaultValue={campaign.currency} required />
                <Field name="vehicle_count" label="Vehicle count" type="number" min={1} required />
              </div>
              <label className="micro text-muted">
                Payment class
                <select
                  name="payment_class"
                  className="border-edge bg-raised mt-1.5 h-11 w-full rounded-lg border px-3.5 text-sm"
                >
                  <option value="standard_prepaid">Standard prepaid</option>
                  <option value="approved_corporate_credit">Approved corporate credit</option>
                </select>
              </label>
              <Field name="payment_terms" label="Payment terms / evidence notes" required />
              <Button type="submit">Record immutable revision</Button>
            </form>
          ) : (
            <p className="text-muted text-sm">The advertiser has not requested a quotation.</p>
          )}
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
                <dd>{commercial.terms.acceptance_method.replaceAll("_", " ")}</dd>
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
              Exact-match evidence confirms and allocates canonical cash.
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
              <Button type="submit">Record and reconcile transfer</Button>
            </form>
          </Panel>

          <Panel className="p-6">
            <div className="flex items-start justify-between gap-3">
              <div>
                <h2 className="font-display text-xl font-semibold">Invoice</h2>
                <p className="micro text-muted mt-1">VAT-itemised immutable invoice facts</p>
              </div>
              <StatusChip
                tone={invoice?.status === "issued" ? "green" : invoice ? "amber" : "default"}
              >
                {invoice?.status ?? "not created"}
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
                <div className="border-edge mt-4 grid gap-3 rounded-lg border p-4 sm:grid-cols-3">
                  <div>
                    <p className="micro text-muted">Effective obligation</p>
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
                    <p className="mt-1 text-sm">{invoice.payment_status.replaceAll("_", " ")}</p>
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
                {invoice.status === "issued" ? (
                  <form
                    action={recordInvoiceCorrectionAction.bind(null, campaignId, invoice.id)}
                    className="border-edge mt-5 grid gap-3 border-t pt-5"
                  >
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
                ) : (
                  <p className="text-amber mt-4 text-sm">
                    Issuance remains disabled until verified statutory issuer facts resolve
                    EXT-Q28-COMPANY.
                  </p>
                )}
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
            <h2 className="font-display text-xl font-semibold">Settlement lineage</h2>
            <p className="micro text-muted mt-1">
              Persisted refund and credit settlements for this campaign
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
                    {settlement.disposition.replaceAll("_", " ")}
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
                  Funding &amp; production authority
                </h2>
                <p className="micro text-muted mt-1">
                  Liability remains distinct from advertiser price.
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
            {!commercial.financial_authority ? (
              <form
                action={recordFinancialAuthorityAction.bind(
                  null,
                  campaignId,
                  commercial.terms.payment_class as
                    "standard_prepaid" | "approved_corporate_credit",
                  me.user.id,
                )}
                className="mt-5 grid gap-4"
              >
                <Field name="max_driver_liability" label="Maximum driver liability" required />
                {commercial.terms.payment_class === "approved_corporate_credit" ? (
                  <>
                    <Field name="credit_limit" label="Approved credit limit" required />
                    <Field name="due_at" label="Credit due at" type="datetime-local" required />
                    <Field name="credit_terms" label="Approved credit terms" required />
                  </>
                ) : null}
                <Field name="reason" label="Authority evidence / reason" required />
                <Button type="submit">Record financial authority</Button>
              </form>
            ) : !commercial.production_start ? (
              <div className="mt-5">
                <p className="text-muted mb-3 text-sm">
                  Standard prepaid starts only after the exact 24-hour boundary, unless the
                  advertiser’s immutable waiver is supplied. The server rechecks the boundary.
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
            ) : (
              <p className="mt-5 text-sm">
                Basis: {commercial.production_start.authority_basis.replaceAll("_", " ")}
              </p>
            )}
          </Panel>

          <Panel className="p-6">
            <div className="flex items-start justify-between gap-3">
              <div>
                <h2 className="font-display text-xl font-semibold">Advertiser budget policy</h2>
                <p className="micro text-muted mt-1">
                  Billing spend—not driver payout cost—will drive enforcement.
                </p>
              </div>
              <StatusChip tone="amber">External policy required</StatusChip>
            </div>
            <p className="text-muted mt-5 text-sm">
              Thresholds, recognition timing, pause/resume and override behavior remain disabled
              under EXT-BUDGET-POLICY. Recording the blocked state creates admin-visible evidence
              without pausing this campaign.
            </p>
            <form action={recordBudgetBlockedStateAction.bind(null, campaignId)} className="mt-4">
              <Button type="submit" variant="ghost">
                Record blocked policy state
              </Button>
            </form>
          </Panel>
        </div>
      ) : null}
    </div>
  );
}
