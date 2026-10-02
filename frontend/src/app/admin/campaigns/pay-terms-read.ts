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
    const versioned = ["payout_v2", "payout_v3", "payout_v4"].includes(rule.formula_version);
    const revisions = versioned
      ? (
          await api.GET("/api/v1/admin/campaigns/{campaign_id}/payout-rules/{rule_id}/revisions", {
            params: {
              path: { campaign_id: campaignId, rule_id: rule.id },
              query: { limit: 1, effective_before: now },
            },
          })
        ).data
      : undefined;
    if (versioned && !revisions) return undefined;
    const current = revisions?.items.find(
      (r) => r.payout_rule_id === rule.id && Date.parse(r.effective_from) <= Date.parse(now),
    );
    const terms = current ?? (!versioned ? rule : undefined);
    const daily = current?.formula_version === "payout_v4";
    const ready = Boolean(
      terms &&
      (daily
        ? current?.daily_rate_naira != null && current.daily_target_miles != null
        : terms.hourly_rate_naira != null && terms.daily_payable_hours_cap != null),
    );
    const summary =
      daily && ready
        ? `${formatMoneyExact(current!.daily_rate_naira, current!.currency)} per day for ${current!.daily_target_miles} miles.`
        : ready
          ? `${formatMoneyExact(terms!.hourly_rate_naira, terms!.currency)} per hour, up to ${terms!.daily_payable_hours_cap} payable hours per day.${current?.premium_hourly_rate_naira != null ? ` ${formatMoneyExact(current.premium_hourly_rate_naira, current.currency)} per hour inside the premium area.` : ""}`
          : versioned
            ? "No pay terms are effective yet."
            : "This campaign still uses older distance and zone pay terms. Review them before offering new work.";
    return { rule, current, summary, ready };
  } catch {
    return undefined;
  }
});
