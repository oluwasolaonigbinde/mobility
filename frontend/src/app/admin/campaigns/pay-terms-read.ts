import { cache } from "react";
import { createApiClient } from "@/lib/api/client";
import { getSessionToken } from "@/lib/auth/session";
import { formatMoneyExact } from "@/lib/format";

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
      return { rule, current: undefined, summary: "No current pay terms recorded.", ready: false };
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
    const ready = Boolean(current?.daily_rate_naira != null && current.daily_target_miles != null);
    const summary = ready
      ? `${formatMoneyExact(current!.daily_rate_naira, current!.currency)} per day for ${current!.daily_target_miles} miles.`
      : "No pay terms are effective yet.";
    return { rule, current, summary, ready };
  } catch {
    return undefined;
  }
});
