import type { Metadata } from "next";
import { requireRole } from "@/lib/auth/current-user";
import { createApiClient } from "@/lib/api/client";
import { getSessionToken } from "@/lib/auth/session";
import { formatCount, formatMoney, formatScore } from "@/lib/format";
import { Stat } from "@/components/ui/stat";

export const metadata: Metadata = { title: "Overview" };

export default async function AdvertiserOverviewPage() {
  const me = await requireRole("advertiser");
  const api = createApiClient(await getSessionToken());
  const { data: summary } = await api.GET("/api/v1/advertiser/dashboard/summary");

  const greeting = new Date().getHours() < 12 ? "Good morning" : "Good evening";
  const costTotal = summary?.costs.totals_by_currency[0];
  const openFlags = summary?.quality.fraud_flags.open ?? 0;

  return (
    <div className="animate-rise mx-auto max-w-6xl">
      <h1 className="font-display text-3xl font-semibold tracking-tight">
        {greeting}, {me.advertiser_organization?.name ?? me.user.full_name}
      </h1>
      <p className="micro text-muted mt-1 mb-8">Campaign overview · aggregate measurement</p>

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-3 xl:grid-cols-6">
        <Stat
          label="Modelled potential contacts"
          value={formatCount(summary?.impressions.estimated_impressions)}
          hint={`${formatCount(summary?.impressions.estimated_trip_count)} estimated trips`}
        />
        <Stat
          label="Model confidence diagnostic"
          value={formatScore(summary?.impressions.average_confidence_score)}
          hint="Formula diagnostic, not a statistical confidence interval"
          tone="cyan"
        />
        <Stat
          label="Active campaigns"
          value={formatCount(summary?.campaigns.active)}
          hint={`${formatCount(summary?.campaigns.total)} total`}
        />
        <Stat
          label="Active vehicles"
          value={formatCount(summary?.assignments.active)}
          tone="amber"
          hint={`${formatCount(summary?.trips.total)} trips recorded`}
        />
        <Stat
          label="Driver campaign cost"
          value={costTotal ? formatMoney(costTotal.final_payout_total, costTotal.currency) : "—"}
          tone="green"
          hint="Payout projection — not advertiser spend"
        />
        <Stat
          label="Open fraud flags"
          value={formatCount(openFlags)}
          tone={openFlags > 0 ? "coral" : "green"}
          hint="Auto-pulled from billable inventory"
        />
      </div>
    </div>
  );
}
