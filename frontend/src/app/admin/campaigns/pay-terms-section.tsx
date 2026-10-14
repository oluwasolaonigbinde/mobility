import { createApiClient } from "@/lib/api/client";
import { getSessionToken } from "@/lib/auth/session";
import { DailyRatePanel } from "../payouts/rules/daily-rate-panel";
import { QueueUnavailable } from "../queue-search";
import { readPayTerms } from "./pay-terms-read";

export default async function PayTermsSection({ campaignId }: { campaignId: string }) {
  const api = createApiClient(await getSessionToken());
  const terms = await readPayTerms(campaignId);
  if (!terms) return <QueueUnavailable />;
  const rule = terms.rule;
  const revisions = rule
    ? await api
        .GET("/api/v1/admin/campaigns/{campaign_id}/payout-rules/{rule_id}/revisions", {
          params: { path: { campaign_id: campaignId, rule_id: rule.id }, query: { limit: 50 } },
        })
        .catch(() => ({ data: undefined }))
    : undefined;
  const publishing = await api
    .GET("/api/v1/admin/payout-v4/status")
    .catch(() => ({ data: undefined }));
  if ((rule && !revisions?.data) || !publishing?.data) return <QueueUnavailable />;
  return (
    <div className="space-y-5">
      <p className="text-lg font-medium">{terms.summary}</p>
      <details>
        <summary className="text-cyan cursor-pointer">Change pay terms</summary>
        <div className="mt-4 space-y-5">
          <DailyRatePanel
            campaignId={campaignId}
            revisions={revisions?.data?.items ?? []}
            publishingEnabled={publishing.data.publishing_enabled}
          />
        </div>
      </details>
    </div>
  );
}
