import type { Metadata } from "next";
import Link from "next/link";
import { createApiClient } from "@/lib/api/client";
import { requireRole } from "@/lib/auth/current-user";
import { getSessionToken } from "@/lib/auth/session";
import { formatDateRange, formatMoney } from "@/lib/format";
import { isCampaignStatus, statusLabel, statusTone } from "@/lib/campaigns/status";
import { PageHeader } from "@/components/ui/page-header";
import { Panel } from "@/components/ui/panel";
import { StatusChip } from "@/components/ui/status-chip";
import { EmptyState } from "@/components/ui/empty-state";
import { Pagination } from "@/components/ui/pagination";
import { FilterChips } from "@/components/ui/tabs";
import { DataUnavailable } from "@/components/ui/data-unavailable";
import { loadAllAdvertiserPages, type UnavailableReason } from "@/lib/advertiser/page-data";
import { bookedBudget, minorDecimal, type BudgetDisplay } from "@/lib/advertiser/budget-display";
import { campaignDay } from "@/lib/campaigns/day-progress";
import { CampaignTimeline } from "@/components/campaigns/campaign-timeline";
import { PortalIcon } from "@/components/brand/portal-icon";

export const metadata: Metadata = { title: "Campaigns" };

/** This campaign's own booked figure (D103); a daily-only campaign has no total to show. */
function BookedCell({ value }: { value: BudgetDisplay | null }) {
  if (!value)
    return (
      <>
        <span aria-hidden="true">—</span>
        <span className="sr-only">not available</span>
      </>
    );
  const booked = formatMoney(minorDecimal(value.booked), value.currency);
  return value.budget === null ? (
    <>{booked}</>
  ) : (
    <>
      {booked}
      <span className="text-muted">
        {" "}
        of {formatMoney(minorDecimal(value.budget), value.currency)}
      </span>
    </>
  );
}

const PAGE_SIZE = 20;

interface SearchParams {
  group?: string;
  offset?: string;
}

const groups = {
  running: { label: "Running", statuses: ["active", "paused"] },
  setup: {
    label: "Being set up",
    statuses: ["draft", "pending_review", "approved", "rejected"],
  },
  finished: { label: "Finished", statuses: ["finished", "cancelled"] },
} as const;
type Group = keyof typeof groups;
function listHref(params: { group?: Group; offset?: number }): string {
  const qs = new URLSearchParams();
  if (params.group && params.group !== "running") qs.set("group", params.group);
  if (params.offset) qs.set("offset", String(params.offset));
  const s = qs.toString();
  return s ? `/advertiser/campaigns?${s}` : "/advertiser/campaigns";
}

export default async function CampaignsPage({
  searchParams,
}: {
  searchParams: Promise<SearchParams>;
}) {
  const params = await searchParams;
  const group: Group =
    params.group === "setup" || params.group === "finished" ? params.group : "running";
  const rawOffset = Number(params.offset ?? 0);
  const offset = Number.isFinite(rawOffset) && rawOffset > 0 ? Math.floor(rawOffset) : 0;

  await requireRole("advertiser");
  const api = createApiClient(await getSessionToken());
  const loaded = await loadAllAdvertiserPages((next) =>
    api.GET("/api/v1/advertiser/campaigns", { params: { query: { limit: 100, offset: next } } }),
  );
  const unavailable = (reason: UnavailableReason) => (
    <DataUnavailable
      title="Campaigns unavailable"
      reason={reason}
      retryHref={listHref({ group, offset })}
    />
  );
  if (!loaded.available) return unavailable(loaded.reason);
  const campaigns = loaded.data;
  if (campaigns.some((campaign) => !isCampaignStatus(campaign.status)))
    return unavailable("protocol");
  const filtered = campaigns.filter((campaign) =>
    (groups[group].statuses as readonly string[]).includes(campaign.status),
  );
  const items = filtered.slice(offset, offset + PAGE_SIZE);
  const total = filtered.length;

  return (
    <div className="animate-rise mx-auto max-w-6xl">
      <PageHeader
        title="Campaigns"
        eyebrow={`${total} campaign${total === 1 ? "" : "s"} · ${groups[group].label}`}
        actions={
          <Link
            href="/advertiser/campaigns/new"
            className="bg-amber text-bg hover:bg-amber-soft shadow-glow-amber inline-flex h-11 items-center rounded-lg px-5 text-sm font-medium transition-colors"
          >
            + New campaign
          </Link>
        }
      />

      <CampaignTimeline campaigns={campaigns} />
      <FilterChips
        label="Campaign groups"
        items={(Object.keys(groups) as Group[]).map((key) => ({
          href: listHref({ group: key }),
          label: groups[key].label,
          active: key === group,
        }))}
      />

      {items.length === 0 ? (
        <EmptyState
          title={
            campaigns.length
              ? `No campaigns ${group === "running" ? "running" : group === "setup" ? "being set up" : "finished"}`
              : "No campaigns yet"
          }
          body={
            campaigns.length
              ? "Choose another tab to see your other campaigns."
              : "Your campaigns will appear here once you’ve set one up."
          }
        />
      ) : (
        <>
          <Panel className="overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full min-w-[640px] text-sm">
                <thead>
                  <tr className="border-edge micro text-muted border-b text-left">
                    <th className="px-5 py-3.5 font-normal">Campaign</th>
                    <th className="px-5 py-3.5 font-normal">Status</th>
                    <th className="px-5 py-3.5 font-normal">Dates</th>
                    <th className="px-5 py-3.5 text-right font-normal">
                      <span className="inline-flex items-center gap-2">
                        <PortalIcon name="wallet" className="size-4" />
                        Booked
                      </span>
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {items.map((c) => (
                    <tr
                      key={c.id}
                      className="border-edge/60 hover:bg-raised/50 border-b transition-colors last:border-0"
                    >
                      <td className="px-5 py-4">
                        <Link
                          href={`/advertiser/campaigns/${c.id}`}
                          className="hover:text-amber font-medium"
                        >
                          {c.name}
                        </Link>
                        {c.description ? (
                          <p className="text-muted mt-0.5 line-clamp-1 text-[15px]">
                            {c.description}
                          </p>
                        ) : null}
                      </td>
                      <td className="px-5 py-4">
                        <StatusChip tone={statusTone[c.status]}>{statusLabel[c.status]}</StatusChip>
                      </td>
                      <td className="text-muted px-5 py-4 text-[15px]">
                        {formatDateRange(c.start_at, c.end_at)}
                        <p className="text-green mt-1 text-sm font-semibold">
                          {campaignDay(c.start_at, c.end_at)}
                        </p>
                      </td>
                      <td className="px-5 py-4 text-right text-[15px] tabular-nums">
                        <BookedCell value={bookedBudget(c)} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Panel>
          <Pagination
            total={total}
            limit={PAGE_SIZE}
            offset={offset}
            hrefFor={(o) => listHref({ group, offset: o })}
          />
        </>
      )}
    </div>
  );
}
