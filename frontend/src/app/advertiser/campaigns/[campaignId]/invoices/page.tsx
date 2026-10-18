import { notFound } from "next/navigation";
import { createApiClient } from "@/lib/api/client";
import { getSessionToken } from "@/lib/auth/session";
import { loadAdvertiserPageData } from "@/lib/advertiser/page-data";
import { CommercialHistory } from "@/lib/billing/commercial-history";
import { DataUnavailable } from "@/components/ui/data-unavailable";
import { EmptyState } from "@/components/ui/empty-state";
import { requireRole, isAdvertiserViewer } from "@/lib/auth/current-user";

export const metadata = { title: "Campaign invoices" };
export default async function CampaignInvoicesPage({
  params,
}: {
  params: Promise<{ campaignId: string }>;
}) {
  const { campaignId } = await params;
  const me = await requireRole("advertiser");
  const api = createApiClient(await getSessionToken());
  const result = await loadAdvertiserPageData(() =>
    api.GET("/api/v1/advertiser/campaigns/{campaign_id}/commercial", {
      params: { path: { campaign_id: campaignId } },
    }),
  );
  if (!result.available) {
    if (result.reason === "missing") notFound();
    return (
      <DataUnavailable
        title="Invoices unavailable"
        reason={result.reason}
        retryHref={`/advertiser/campaigns/${campaignId}/invoices`}
      />
    );
  }
  return (
    <div>
      <h1 className="font-display mb-5 text-3xl font-semibold">Invoices</h1>
      {!result.data.invoices.length && !result.data.settlements.length ? (
        <EmptyState
          title="No invoices yet"
          body="When Terrax Media sends an invoice, you’ll find it here."
        />
      ) : (
        <CommercialHistory
          invoices={result.data.invoices}
          settlements={result.data.settlements}
          showPayment={!isAdvertiserViewer(me)}
        />
      )}
    </div>
  );
}
