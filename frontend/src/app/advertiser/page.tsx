import type { Metadata } from "next";
import Link from "next/link";
import { requireRole } from "@/lib/auth/current-user";
import { createApiClient } from "@/lib/api/client";
import { getSessionToken } from "@/lib/auth/session";
import { formatCount, formatMoney } from "@/lib/format";
import { Stat } from "@/components/ui/stat";
import { Panel } from "@/components/ui/panel";
import { StatusChip } from "@/components/ui/status-chip";
import { DataUnavailable } from "@/components/ui/data-unavailable";
import { loadAdvertiserPageData } from "@/lib/advertiser/page-data";
import { statusLabel, statusTone } from "@/lib/campaigns/status";

export const metadata: Metadata = { title: "Overview" };

export default async function AdvertiserOverviewPage() {
  const me = await requireRole("advertiser");
  const api = createApiClient(await getSessionToken());
  const [summaryResult, campaignsResult] = await Promise.all([
    loadAdvertiserPageData(() => api.GET("/api/v1/advertiser/dashboard/summary")),
    loadAdvertiserPageData(() =>
      api.GET("/api/v1/advertiser/campaigns", {
        params: { query: { limit: 5, offset: 0 } },
      }),
    ),
  ]);
  const summary = summaryResult.available ? summaryResult.data : undefined;

  const greeting = new Date().getHours() < 12 ? "Good morning" : "Good evening";
  const costTotal = summary?.costs.totals_by_currency[0];
  const openFlags = summary?.quality.fraud_flags.open;

  return (
    <div className="animate-rise mx-auto max-w-6xl">
      <h1 className="font-display text-3xl font-semibold tracking-tight">
        {greeting}, {me.advertiser_organization?.name ?? me.user.full_name}
      </h1>
      <p className="micro text-muted mt-1 mb-8">Campaign overview</p>

      {summaryResult.available ? (
        <div className="grid grid-cols-2 gap-4 lg:grid-cols-3 xl:grid-cols-5">
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
            label="Estimated ad exposure"
            value={formatCount(summary?.impressions.estimated_impressions)}
            tone="cyan"
            hint="Estimated opportunities to see the ad, based on routes and traffic. This is not a count of people or measured views."
          />
          <Stat
            label="Driver pay to date"
            className="max-sm:[&>p:nth-child(2)]:text-2xl"
            value={costTotal ? formatMoney(costTotal.final_payout_total, costTotal.currency) : "—"}
            tone="green"
            hint="Calculated driver pay; your invoice is shown in Billing."
          />
          <Stat
            label="Open fraud flags"
            value={formatCount(openFlags)}
            tone={openFlags !== undefined && openFlags > 0 ? "coral" : "green"}
            hint="Trip integrity checks awaiting Cardvert review"
          />
        </div>
      ) : (
        <DataUnavailable
          title="Campaign results unavailable"
          reason={summaryResult.reason}
          retryHref="/advertiser"
        />
      )}

      {campaignsResult.available ? (
        <Panel className="mt-6 overflow-hidden" aria-label="Recent campaigns">
          <div className="border-edge flex flex-wrap items-center justify-between gap-3 border-b px-6 py-4">
            <h2 className="font-display text-xl font-semibold">Recent campaigns</h2>
            <Link href="/advertiser/campaigns" className="micro text-amber hover:underline">
              View all {formatCount(campaignsResult.data.total)} campaigns →
            </Link>
          </div>
          {campaignsResult.data.items.length ? (
            <ul className="divide-edge divide-y">
              {campaignsResult.data.items.map((campaign) => (
                <li
                  key={campaign.id}
                  className="flex flex-wrap items-center justify-between gap-3 px-6 py-4"
                >
                  <Link
                    href={`/advertiser/campaigns/${campaign.id}`}
                    className="hover:text-amber font-medium"
                  >
                    {campaign.name}
                  </Link>
                  <StatusChip tone={statusTone[campaign.status]}>
                    {statusLabel[campaign.status]}
                  </StatusChip>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-muted px-6 py-6 text-sm">No campaigns yet.</p>
          )}
        </Panel>
      ) : (
        <DataUnavailable
          className="mt-6"
          title="Campaigns unavailable"
          reason={campaignsResult.reason}
          retryHref="/advertiser"
        />
      )}
    </div>
  );
}
