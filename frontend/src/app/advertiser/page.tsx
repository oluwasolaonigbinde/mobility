import type { Metadata } from "next";
import Image from "next/image";
import Link from "next/link";
import { requireRole } from "@/lib/auth/current-user";
import { createApiClient } from "@/lib/api/client";
import { getSessionToken } from "@/lib/auth/session";
import { formatCount, formatDateRange } from "@/lib/format";
import { Panel } from "@/components/ui/panel";
import { DataUnavailable } from "@/components/ui/data-unavailable";
import { loadAdvertiserPageData } from "@/lib/advertiser/page-data";
import { CampaignArtwork } from "@/components/campaigns/campaign-artwork";

export const metadata: Metadata = { title: "Home" };

export default async function AdvertiserOverviewPage() {
  const me = await requireRole("advertiser");
  const api = createApiClient(await getSessionToken());
  const [summary, first] = await Promise.all([
    loadAdvertiserPageData(() => api.GET("/api/v1/advertiser/dashboard/summary")),
    loadAdvertiserPageData(() =>
      api.GET("/api/v1/advertiser/campaigns", {
        params: { query: { status: "active", limit: 100, offset: 0 } },
      }),
    ),
  ]);
  let inventory = first;
  if (first.available) {
    const items = [...first.data.items];
    while (items.length < first.data.total) {
      const page = await loadAdvertiserPageData(() =>
        api.GET("/api/v1/advertiser/campaigns", {
          params: { query: { status: "active", limit: 100, offset: items.length } },
        }),
      );
      if (!page.available) {
        inventory = page;
        break;
      }
      if (
        !page.data.items.length ||
        page.data.total !== first.data.total ||
        page.data.items.some((next) => items.some((item) => item.id === next.id))
      ) {
        inventory = { available: false, reason: "protocol" };
        break;
      }
      items.push(...page.data.items);
    }
    if (inventory.available) inventory = { available: true, data: { ...first.data, items } };
  }
  // The list read carries each card's picture and area count, so cards need no more reads (REQ-208).
  const cards = inventory.available ? inventory.data.items : [];
  const start = (
    <Link href="/advertiser/campaigns/new" className="brand-action w-full sm:w-auto">
      Start a new campaign <span aria-hidden="true">→</span>
    </Link>
  );
  return (
    <div className="animate-rise mx-auto max-w-6xl">
      <div className="mb-7 flex flex-wrap items-end justify-between gap-5">
        <div>
          <h1 className="font-display max-w-xl text-3xl font-semibold md:text-[2.5rem]">
            Welcome back, {me.advertiser_organization?.name ?? me.user.full_name}
          </h1>
          {inventory.available ? (
            <p className="text-ink mt-3 text-base md:text-lg">
              {inventory.data.total
                ? `${formatCount(inventory.data.total)} ${inventory.data.total === 1 ? "campaign is" : "campaigns are"} on the road right now.`
                : "No campaigns are running right now."}
            </p>
          ) : null}
        </div>
        {start}
      </div>
      <Panel
        className="mb-9 grid grid-cols-2 gap-y-5 p-5 md:p-7"
        aria-label="Running campaign figures"
      >
        <div className="pr-4">
          <p className="text-ink text-base font-medium">Running campaigns</p>
          <p className="font-display mt-2 text-3xl font-semibold">
            {inventory.available ? formatCount(inventory.data.total) : "—"}
          </p>
        </div>
        <div className="border-edge border-l pl-5 md:pl-7">
          <p className="text-ink text-base font-medium">Cars on the road</p>
          <p className="font-display mt-2 text-3xl font-semibold">
            {summary.available ? formatCount(summary.data.assignments.active) : "—"}
          </p>
        </div>
      </Panel>
      {!summary.available ? (
        <DataUnavailable
          title="Campaign results unavailable"
          reason={summary.reason}
          retryHref="/advertiser"
          className="mb-5"
        />
      ) : null}
      <div className="mb-4 flex items-center justify-between gap-3">
        <h2 className="font-display text-xl font-semibold">On the road now</h2>
        <Link href="/advertiser/campaigns" className="text-green text-base font-semibold">
          All campaigns →
        </Link>
      </div>
      {!inventory.available ? (
        <DataUnavailable
          title="Campaigns unavailable"
          reason={inventory.reason}
          retryHref="/advertiser"
        />
      ) : !cards.length ? (
        <Panel className="flex flex-col items-center p-8 text-center">
          <Image
            src="/marketing/terrax/fleet-corridor-placeholder.svg"
            width={1280}
            height={720}
            alt="Illustration of cars carrying adverts through a city"
            className="mb-6 h-40 w-full max-w-sm rounded-2xl object-cover"
          />
          <h3 className="font-display text-2xl font-semibold">No campaigns running</h3>
          <p className="text-ink mt-3 max-w-md text-base">
            Your running campaigns will appear here.
          </p>
        </Panel>
      ) : (
        <div className="grid gap-6">
          {cards.map((campaign) => (
            <Panel key={campaign.id} className="overflow-hidden">
              <div className="h-48 md:h-56">
                <CampaignArtwork name={campaign.name} fileId={campaign.preview_file_id} />
              </div>
              <div className="flex flex-wrap items-center justify-between gap-5 p-5 md:p-6">
                <div>
                  <p className="text-green mb-2 flex items-center gap-2 text-sm font-semibold">
                    <span className="bg-green size-1.5 rounded-full" />
                    Running
                  </p>
                  <h3 className="font-display text-lg font-semibold">
                    <Link
                      href={`/advertiser/campaigns/${campaign.id}`}
                      className="hover:text-green"
                    >
                      {campaign.name}
                    </Link>
                  </h3>
                  <p className="text-muted mt-2 text-base">
                    {formatDateRange(campaign.start_at, campaign.end_at)}
                  </p>
                  <p className="text-muted mt-1 text-base">
                    {campaign.target_zone_count === 1
                      ? "1 target area"
                      : `${formatCount(campaign.target_zone_count)} target areas`}
                  </p>
                </div>
                <Link href={`/advertiser/campaigns/${campaign.id}`} className="brand-secondary">
                  View campaign →
                </Link>
              </div>
            </Panel>
          ))}
        </div>
      )}
    </div>
  );
}
