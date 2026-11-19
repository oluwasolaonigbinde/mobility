import { createApiClient } from "@/lib/api/client";
import { getSessionToken } from "@/lib/auth/session";
import { requireRole } from "@/lib/auth/current-user";
import { Reports } from "./report-list";
import { loadAllAdvertiserPages } from "@/lib/advertiser/page-data";
import { DataUnavailable } from "@/components/ui/data-unavailable";
import { PageHeader } from "@/components/ui/page-header";

export const metadata = { title: "Reports" };

export default async function ReportsPage() {
  const me = await requireRole("advertiser");
  const sessionScope = `${me.user.id}:${me.advertiser_organization?.id}`;
  const api = createApiClient(await getSessionToken());
  const result = await loadAllAdvertiserPages((offset) =>
    api.GET("/api/v1/advertiser/campaigns", {
      params: { query: { limit: 100, offset } },
    }),
  );
  if (!result.available)
    return (
      <DataUnavailable
        title="Reports unavailable"
        reason={result.reason}
        retryHref="/advertiser/reports"
      />
    );
  const now = new Date();
  const campaigns = result.data
    .filter(
      ({ status, start_at }) =>
        ["active", "paused", "finished", "cancelled"].includes(status) &&
        start_at != null &&
        Date.parse(start_at) <= now.getTime(),
    )
    .map(({ id, name }) => ({ id, name }));
  const today = new Intl.DateTimeFormat("en-CA", { timeZone: "Africa/Lagos" }).format(now);
  return (
    <div className="space-y-6">
      <PageHeader title="Reports" />
      <Reports key={sessionScope} sessionScope={sessionScope} campaigns={campaigns} today={today} />
    </div>
  );
}
