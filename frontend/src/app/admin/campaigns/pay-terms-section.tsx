import { createApiClient } from "@/lib/api/client";
import { getSessionToken } from "@/lib/auth/session";
import { RuleForm } from "../payouts/rules/rule-form";
import { RevisionsPanel } from "../payouts/rules/revisions-panel";
import { DailyRatePanel } from "../payouts/rules/daily-rate-panel";
import { QueueUnavailable } from "../queue-search";
import { readPayTerms } from "./pay-terms-read";

export default async function PayTermsSection({ campaignId }: { campaignId: string }) {
  const api = createApiClient(await getSessionToken());
  const terms = await readPayTerms(campaignId);
  if (!terms) return <QueueUnavailable />;
  const rule = terms.rule;
  const versioned = Boolean(
    rule && ["payout_v2", "payout_v3", "payout_v4"].includes(rule.formula_version),
  );
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
      <p className="text-lg font-medium">{terms.summary}</p>
      <details>
        <summary className="text-cyan cursor-pointer">Change pay terms</summary>
        <div className="mt-4 space-y-5">
          {rule && daily ? null : rule && versioned ? (
            <RevisionsPanel
              campaignId={campaignId}
              ruleId={rule.id}
              revisions={revisions?.data?.items ?? []}
            />
          ) : rule ? (
            <RuleForm campaignId={campaignId} rule={rule} />
          ) : null}
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
      </details>
    </div>
  );
}
