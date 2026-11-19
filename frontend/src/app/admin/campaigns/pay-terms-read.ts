import { adminValueFailure } from "@/lib/api/admin-read";
import { cache } from "react";
import type { components } from "@/lib/api/schema";
import { createApiClient } from "@/lib/api/client";
import { getSessionToken } from "@/lib/auth/session";
import { formatMoneyExact } from "@/lib/format";

type Revision = components["schemas"]["CampaignPayoutRuleRevisionRead"];

function hasCompletePayTerms(
  revision: Revision | undefined,
  currency: string,
): revision is Revision {
  return (
    revision != null &&
    revision.formula_version === "payout_v4" &&
    revision.currency === currency &&
    revision.daily_rate_naira != null &&
    revision.daily_target_miles != null &&
    revision.shortfall_strategy != null &&
    revision.minimum_miles != null &&
    revision.outside_area_weight != null
  );
}

/** One request-local selection feeds the summary and launch checklist. */
export const readPayTerms = cache(async (campaignId: string) => {
  const now = new Date().toISOString();
  const api = createApiClient(await getSessionToken());
  try {
    const { data } = await api.GET("/api/v1/admin/campaigns/{campaign_id}/payout-rules", {
      params: { path: { campaign_id: campaignId }, query: { limit: 100 } },
    });
    if (!data) return undefined;
    const rule = data.items.find((r) => r.status === "active");
    if (!rule)
      return {
        rule,
        current: undefined,
        summary: "No current pay terms recorded.",
        ready: false,
        startsAt: undefined,
      };
    const { data: revisions } = await api.GET(
      "/api/v1/admin/campaigns/{campaign_id}/payout-rules/{rule_id}/revisions",
      {
        params: {
          path: { campaign_id: campaignId, rule_id: rule.id },
          query: { limit: 1, effective_before: now },
        },
      },
    );
    if (!revisions) return undefined;
    const current = revisions?.items.find(
      (r) => r.payout_rule_id === rule.id && Date.parse(r.effective_from) <= Date.parse(now),
    );
    const ready = hasCompletePayTerms(current, rule.currency);
    let startsAt: string | undefined;
    if (!ready) {
      const path = { campaign_id: campaignId, rule_id: rule.id };
      const upcoming = await api.GET(
        "/api/v1/admin/campaigns/{campaign_id}/payout-rules/{rule_id}/revisions",
        { params: { path, query: { limit: 1 } } },
      );
      const futureCount = (upcoming.data?.total ?? 0) - revisions.total;
      const first =
        futureCount > 1
          ? (
              await api.GET(
                "/api/v1/admin/campaigns/{campaign_id}/payout-rules/{rule_id}/revisions",
                { params: { path, query: { limit: 1, offset: futureCount - 1 } } },
              )
            ).data?.items[0]
          : upcoming.data?.items[0];
      if (
        hasCompletePayTerms(first, rule.currency) &&
        first.payout_rule_id === rule.id &&
        Date.parse(first.effective_from) > Date.parse(now)
      ) {
        startsAt = first.effective_from;
      }
    }
    const summary = ready
      ? `${formatMoneyExact(current.daily_rate_naira, current.currency)} per day for ${Number(current.daily_target_miles)} miles.`
      : "No pay terms are effective yet.";
    return { rule, current, summary, ready, startsAt };
  } catch (error) {
    adminValueFailure(error);
    return undefined;
  }
});
