import type { Metadata } from "next";
import Link from "next/link";
import { createApiClient } from "@/lib/api/client";
import { getSessionToken } from "@/lib/auth/session";
import { formatDateRange, formatMoney } from "@/lib/format";
import {
  isCampaignStatus,
  statusLabel,
  statusTone,
  CAMPAIGN_STATUSES,
} from "@/lib/campaigns/status";
import { PageHeader } from "@/components/ui/page-header";
import { Panel } from "@/components/ui/panel";
import { StatusChip } from "@/components/ui/status-chip";
import { EmptyState } from "@/components/ui/empty-state";
import { Pagination } from "@/components/ui/pagination";
import { cx } from "@/lib/cx";

export const metadata: Metadata = { title: "Campaigns" };

const PAGE_SIZE = 20;

interface SearchParams {
  status?: string;
  offset?: string;
}

function listHref(params: { status?: string; offset?: number }): string {
  const qs = new URLSearchParams();
  if (params.status) qs.set("status", params.status);
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
  const status = params.status && isCampaignStatus(params.status) ? params.status : undefined;
  const rawOffset = Number(params.offset ?? 0);
  const offset = Number.isFinite(rawOffset) && rawOffset > 0 ? Math.floor(rawOffset) : 0;

  const api = createApiClient(await getSessionToken());
  const { data } = await api.GET("/api/v1/advertiser/campaigns", {
    params: { query: { limit: PAGE_SIZE, offset, ...(status ? { status } : {}) } },
  });

  const items = data?.items ?? [];
  const total = data?.total ?? 0;

  return (
    <div className="animate-rise mx-auto max-w-6xl">
      <PageHeader
        title="Campaigns"
        eyebrow={`${total} campaign${total === 1 ? "" : "s"}${status ? ` · ${statusLabel[status]}` : ""}`}
        actions={
          <Link
            href="/advertiser/campaigns/new"
            className="bg-amber text-bg hover:bg-amber-soft shadow-glow-amber inline-flex h-11 items-center rounded-lg px-5 text-sm font-medium transition-colors"
          >
            + New campaign
          </Link>
        }
      />

      {/* Status filter */}
      <div className="mb-4 flex gap-1 overflow-x-auto" role="group" aria-label="Filter by status">
        <Link
          href={listHref({})}
          className={cx(
            "micro rounded-lg px-3 py-2 whitespace-nowrap transition-colors",
            !status ? "bg-raised text-amber" : "text-muted hover:text-ink",
          )}
        >
          All
        </Link>
        {CAMPAIGN_STATUSES.map((s) => (
          <Link
            key={s}
            href={listHref({ status: s })}
            className={cx(
              "micro rounded-lg px-3 py-2 whitespace-nowrap transition-colors",
              status === s ? "bg-raised text-amber" : "text-muted hover:text-ink",
            )}
          >
            {statusLabel[s]}
          </Link>
        ))}
      </div>

      {items.length === 0 ? (
        <EmptyState
          title={status ? `No ${statusLabel[status].toLowerCase()} campaigns` : "No campaigns yet"}
          body={
            status
              ? "Try a different status filter, or create a new campaign."
              : "Create your first campaign to put your brand on the street."
          }
          action={
            <Link href="/advertiser/campaigns/new" className="micro text-amber hover:underline">
              Create a campaign →
            </Link>
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
                    <th className="px-5 py-3.5 font-normal">Window</th>
                    <th className="px-5 py-3.5 text-right font-normal">Budget</th>
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
                          <p className="text-muted mt-0.5 line-clamp-1 text-xs">{c.description}</p>
                        ) : null}
                      </td>
                      <td className="px-5 py-4">
                        <StatusChip tone={statusTone[c.status]}>{statusLabel[c.status]}</StatusChip>
                      </td>
                      <td className="text-muted px-5 py-4 font-mono text-xs">
                        {formatDateRange(c.start_at, c.end_at)}
                      </td>
                      <td className="px-5 py-4 text-right font-mono text-xs">
                        {formatMoney(c.budget_amount, c.currency)}
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
            hrefFor={(o) => listHref({ status, offset: o })}
          />
        </>
      )}
    </div>
  );
}
