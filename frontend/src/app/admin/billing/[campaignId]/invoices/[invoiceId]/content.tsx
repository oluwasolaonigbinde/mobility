import Link from "next/link";
import { notFound } from "next/navigation";
import { ApiError } from "@/lib/api/errors";
import { requireRole } from "@/lib/auth/current-user";
import { InvoiceDocument } from "@/lib/billing/invoice-document";
import { QueueUnavailable } from "../../../../queue-search";
import { readCampaign, readCampaignCommercial } from "../../../../entity-reads";

export default async function AdminInvoicePage({
  params,
}: {
  params: Promise<{ campaignId: string; invoiceId: string }>;
}) {
  const { campaignId, invoiceId } = await params;
  await requireRole("admin");
  let campaign, commercial;
  try {
    [{ data: campaign }, { data: commercial }] = await Promise.all([
      readCampaign(campaignId),
      readCampaignCommercial(campaignId),
    ]);
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) notFound();
    return <QueueUnavailable />;
  }
  const invoice = commercial?.invoices.find((candidate) => candidate.id === invoiceId);
  if (!campaign || !commercial || !invoice) notFound();

  return (
    <div className="animate-rise mx-auto max-w-5xl">
      <nav className="micro text-muted mb-4">
        <Link href="/admin/campaigns">Campaigns</Link> /{" "}
        <Link href={`/admin/campaigns/${campaignId}#money`}>{campaign.name}</Link> / Invoice
      </nav>
      <InvoiceDocument
        invoice={invoice}
        terms={commercial.terms ?? null}
        campaignName={campaign.name}
      />
    </div>
  );
}
