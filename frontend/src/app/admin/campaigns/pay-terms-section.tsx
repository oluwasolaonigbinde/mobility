import { createApiClient } from "@/lib/api/client";
import { getSessionToken } from "@/lib/auth/session";
import { RuleForm } from "../payouts/rules/rule-form";
import { RevisionsPanel } from "../payouts/rules/revisions-panel";
import { DailyRatePanel } from "../payouts/rules/daily-rate-panel";
import { QueueUnavailable } from "../queue-search";

export default async function PayTermsSection({ campaignId }: { campaignId: string }) {
  const api = createApiClient(await getSessionToken());
  const { data } = await api
    .GET("/api/v1/admin/campaigns/{campaign_id}/payout-rules", {
      params: { path: { campaign_id: campaignId }, query: { limit: 100 } },
    })
    .catch(() => ({ data: undefined }));
  if (!data) return <QueueUnavailable />;
  const rule = data.items.find((r) => r.status === "active");
  const versioned = rule?.formula_version === "payout_v2" || rule?.formula_version === "payout_v4";
  const daily = rule?.formula_version === "payout_v4";
  const revisions =
    rule && versioned
      ? await api
          .GET("/api/v1/admin/campaigns/{campaign_id}/payout-rules/{rule_id}/revisions", {
            params: { path: { campaign_id: campaignId, rule_id: rule.id }, query: { limit: 50 } },
          })
          .catch(() => ({ data: undefined }))
      : undefined;
  const publishing =
    !rule || daily
      ? await api.GET("/api/v1/admin/payout-v4/status").catch(() => ({ data: undefined }))
      : undefined;
  if ((rule && versioned && !revisions?.data) || ((!rule || daily) && !publishing?.data))
    return <QueueUnavailable />;
  return (
    <div className="space-y-5">
      {rule && daily ? null : rule && versioned ? (
        <RevisionsPanel
          campaignId={campaignId}
          ruleId={rule.id}
          revisions={revisions?.data?.items ?? []}
        />
      ) : (
        <RuleForm campaignId={campaignId} rule={rule ?? null} />
      )}
      {!rule || daily ? (
        publishing?.data && (!daily || revisions?.data) ? (
          <DailyRatePanel
            campaignId={campaignId}
            revisions={revisions?.data?.items ?? []}
            publishingEnabled={publishing.data.publishing_enabled}
          />
        ) : (
          <QueueUnavailable />
        )
      ) : null}
    </div>
  );
}
