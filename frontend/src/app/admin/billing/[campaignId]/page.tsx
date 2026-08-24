import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { createApiClient } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import { getSessionToken } from "@/lib/auth/session";
import { formatMoney } from "@/lib/format";
import { Button } from "@/components/ui/button";
import { Field } from "@/components/ui/field";
import { PageHeader } from "@/components/ui/page-header";
import { Panel } from "@/components/ui/panel";
import { StatusChip } from "@/components/ui/status-chip";
import { recordRevisionAction } from "./actions";

export const metadata: Metadata = { title: "Campaign billing" };

export default async function AdminCampaignBillingPage({
  params,
  searchParams,
}: {
  params: Promise<{ campaignId: string }>;
  searchParams: Promise<{ error?: string; saved?: string }>;
}) {
  const { campaignId } = await params;
  const notice = await searchParams;
  const api = createApiClient(await getSessionToken());
  let campaign, commercial;
  try {
    [{ data: campaign }, { data: commercial }] = await Promise.all([
      api.GET("/api/v1/admin/campaigns/{campaign_id}", {
        params: { path: { campaign_id: campaignId } },
      }),
      api.GET("/api/v1/admin/campaigns/{campaign_id}/commercial", {
        params: { path: { campaign_id: campaignId } },
      }),
    ]);
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) notFound();
    throw error;
  }
  if (!campaign || !commercial) notFound();
  const latest = commercial.revisions.at(-1);
  const revisionAction = commercial.quote_request
    ? recordRevisionAction.bind(null, campaignId, commercial.quote_request.id)
    : undefined;

  return (
    <div className="animate-rise mx-auto max-w-6xl">
      <nav className="micro text-muted mb-4">
        <Link href="/admin/billing">Billing</Link> / {campaign.name}
      </nav>
      <PageHeader title={campaign.name} eyebrow={campaign.organization.name} />
      {notice.error ? <p className="text-coral mb-4 text-sm">{notice.error}</p> : null}
      <div className="grid gap-6 lg:grid-cols-2">
        <Panel className="p-6">
          <div className="mb-4 flex items-center justify-between gap-3">
            <h2 className="font-display text-xl font-semibold">Quotation</h2>
            <StatusChip tone={commercial.terms ? "green" : latest ? "amber" : "default"}>
              {commercial.terms ? "Accepted" : latest ? "Sent" : commercial.quote_request ? "Requested" : "No request"}
            </StatusChip>
          </div>
          {latest ? (
            <dl className="space-y-3 text-sm">
              <div><dt className="micro text-muted">Reference</dt><dd>{latest.quote_reference} · revision {latest.revision_number}</dd></div>
              <div><dt className="micro text-muted">Gross</dt><dd className="font-mono">{formatMoney(latest.gross_amount, latest.currency)}</dd></div>
              <div><dt className="micro text-muted">Payment</dt><dd>{latest.payment_class.replaceAll("_", " ")}</dd></div>
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
              <label className="micro text-muted">Payment class
                <select name="payment_class" className="border-edge bg-raised mt-1.5 h-11 w-full rounded-lg border px-3.5 text-sm">
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
              <div><dt className="micro text-muted">Accepted total</dt><dd className="font-mono">{formatMoney(commercial.terms.gross_amount, commercial.terms.currency)}</dd></div>
              <div><dt className="micro text-muted">Acceptance</dt><dd>{commercial.terms.acceptance_method.replaceAll("_", " ")}</dd></div>
              <div><dt className="micro text-muted">Production wait</dt><dd>{commercial.terms.standard_production_wait_hours} hours</dd></div>
            </dl>
          ) : <p className="text-muted mt-4 text-sm">No accepted terms yet.</p>}
        </Panel>
      </div>
    </div>
  );
}
