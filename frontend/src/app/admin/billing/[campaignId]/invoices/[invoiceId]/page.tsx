import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { createApiClient } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import { requireRole } from "@/lib/auth/current-user";
import { getSessionToken } from "@/lib/auth/session";
import { InvoiceDocument } from "@/lib/billing/invoice-document";

export const metadata: Metadata = { title: "Invoice" };

export default async function AdminInvoicePage({
  params,
}: {
  params: Promise<{ campaignId: string; invoiceId: string }>;
}) {
  const { campaignId, invoiceId } = await params;
  await requireRole("admin");
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
  const invoice = commercial?.invoices.find((candidate) => candidate.id === invoiceId);
  if (!campaign || !commercial || !invoice) notFound();

  return (
    <div className="animate-rise mx-auto max-w-5xl">
      <nav className="micro text-muted mb-4">
        <Link href="/admin/billing">Billing</Link> /{" "}
        <Link href={`/admin/billing/${campaignId}`}>{campaign.name}</Link> / Invoice
      </nav>
      <InvoiceDocument
        invoice={invoice}
        terms={commercial.terms ?? null}
        campaignName={campaign.name}
      />
    </div>
  );
}
