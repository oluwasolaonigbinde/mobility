import { notFound } from "next/navigation";
import { createApiClient } from "@/lib/api/client";
import { getSessionToken } from "@/lib/auth/session";
import { requireRole } from "@/lib/auth/current-user";
import { Reports } from "../../../reports/report-list";
import { loadAdvertiserPageData } from "@/lib/advertiser/page-data";
import { DataUnavailable } from "@/components/ui/data-unavailable";
import { PageHeader } from "@/components/ui/page-header";

export const metadata = { title: "Campaign reports" };

export default async function CampaignReportPage({
  params,
}: {
  params: Promise<{ campaignId: string }>;
}) {
  const { campaignId } = await params;
  const me = await requireRole("advertiser");
  const sessionScope = `${me.user.id}:${me.advertiser_organization?.id}`;
  const api = createApiClient(await getSessionToken());
  const result = await loadAdvertiserPageData(() =>
    api.GET("/api/v1/advertiser/campaigns/{campaign_id}", {
      params: { path: { campaign_id: campaignId } },
    }),
  );
  if (!result.available) {
    if (result.reason === "missing") notFound();
    return (
      <DataUnavailable
        title="Reports unavailable"
        reason={result.reason}
        retryHref={`/advertiser/campaigns/${campaignId}/report`}
      />
    );
  }
  const data = result.data;
  const today = new Intl.DateTimeFormat("en-CA", { timeZone: "Africa/Lagos" }).format(new Date());
  return (
    <div className="space-y-6">
      <PageHeader title={`${data.name} reports`} />
      <Reports
        key={sessionScope}
        sessionScope={sessionScope}
        campaigns={[{ id: data.id, name: data.name }]}
        today={today}
        campaignId={campaignId}
      />
    </div>
  );
}
