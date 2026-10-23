import type { Metadata } from "next";
import Link from "next/link";
import { requireRole } from "@/lib/auth/current-user";
import { createApiClient } from "@/lib/api/client";
import { getSessionToken } from "@/lib/auth/session";
import { formatCount, formatDateRange } from "@/lib/format";
import { Panel } from "@/components/ui/panel";
import { DataUnavailable } from "@/components/ui/data-unavailable";
import { loadAllAdvertiserPages } from "@/lib/advertiser/page-data";
import { loadCampaignAreas } from "@/lib/advertiser/campaign-visuals";
import { loadLivePositions } from "@/lib/advertiser/engagement";
import { loadPerformance } from "@/lib/advertiser/performance";
import { CampaignArtwork } from "@/components/campaigns/campaign-artwork";
import { CampaignMap } from "@/components/campaigns/campaign-map";
import { PerformanceCard } from "@/components/campaigns/performance-card";
import { IconTile, PortalIcon } from "@/components/brand/portal-icon";
import { campaignDay } from "@/lib/campaigns/day-progress";

export const metadata: Metadata = { title: "Home" };

export default async function AdvertiserOverviewPage() {
  const me = await requireRole("advertiser");
  const api = createApiClient(await getSessionToken());
  const inventory = await loadAllAdvertiserPages((offset) =>
    api.GET("/api/v1/advertiser/campaigns", {
      params: { query: { limit: 100, offset } },
    }),
  );
  const campaigns = inventory.available
    ? inventory.data.filter((campaign) => campaign.status === "active")
    : [];
  const loadCard = async (campaign: (typeof campaigns)[number]) => {
    const [areas, live, performance] = await Promise.all([
      loadCampaignAreas(api, campaign.id),
      loadLivePositions(api, campaign.id),
      loadPerformance(api, campaign.id),
    ]);
    return { campaign, areas, live, performance };
  };
  const cards: Awaited<ReturnType<typeof loadCard>>[] = [];
  for (let index = 0; index < campaigns.length; index += 4)
    cards.push(...(await Promise.all(campaigns.slice(index, index + 4).map(loadCard))));
  const liveAvailable =
    inventory.available &&
    cards.every(({ campaign, live }) => live.available && live.data.campaign_id === campaign.id);
  const carCount = liveAvailable
    ? cards.reduce(
        (total, card) => total + (card.live.available ? card.live.data.positions.length : 0),
        0,
      )
    : null;
  const company = me.advertiser_organization?.name ?? me.user.full_name;
  const empty = inventory.available && !inventory.data.length;
  return (
    <div className="animate-rise mx-auto max-w-6xl">
      <section className="portal-hero mb-6">
        <div className="portal-hero-copy">
          <h1>
            {empty ? "Welcome to Cardvert," : "Welcome back,"} <em>{company}</em>
          </h1>
          <p className="mt-3 mb-5 text-base leading-7 text-[#e4f0df] md:text-lg">
            {empty
              ? "Set up your first campaign to get your brand on the road."
              : inventory.available
                ? `${formatCount(campaigns.length)} ${campaigns.length === 1 ? "campaign is" : "campaigns are"} on the road right now.`
                : "Your campaigns, out in the city."}
          </p>
          <Link href="/advertiser/campaigns/new" className="brand-action">
            {empty ? "Start your first campaign" : "Start a new campaign"}{" "}
            <span aria-hidden="true">→</span>
          </Link>
        </div>
        <div className="portal-hero-art" aria-hidden="true" />
      </section>
      <section className="mb-8 grid gap-4 sm:grid-cols-2" aria-label="Running campaign figures">
        <Panel className="portal-card flex gap-4 p-5 md:p-6">
          <IconTile name="megaphone" />
          <div>
            <p>Running campaigns</p>
            <p className="font-display mt-1 text-3xl font-semibold">
              {inventory.available ? formatCount(campaigns.length) : "—"}
            </p>
          </div>
        </Panel>
        <Panel className="portal-card flex gap-4 p-5 md:p-6">
          <IconTile name="car" tone="coral" />
          <div>
            <p>Cars on the road</p>
            <p className="font-display mt-1 text-3xl font-semibold">{formatCount(carCount)}</p>
            <p className="text-muted mt-1 text-sm">As of about 15 minutes ago</p>
          </div>
        </Panel>
      </section>
      <section className="portal-zone">
        <div className="mb-5 flex items-center justify-between gap-3">
          <h2 className="font-display text-xl font-semibold">
            {empty ? "Your campaigns" : "On the road now"}
          </h2>
          <div className="flex flex-wrap justify-end gap-4">
            <Link href="/advertiser/campaigns" className="text-green text-sm font-semibold">
              All campaigns →
            </Link>
          </div>
        </div>
        {!inventory.available ? (
          <DataUnavailable
            title="Campaigns unavailable"
            reason={inventory.reason}
            retryHref="/advertiser"
          />
        ) : !campaigns.length ? (
          <Panel className="flex flex-col items-center p-8 text-center">
            <IconTile name="megaphone" />
            <h3 className="font-display mt-5 text-xl font-semibold">
              {empty ? "No campaigns yet" : "No campaigns running"}
            </h3>
            <p className="text-muted mt-2 text-base">
              {empty
                ? "Your campaigns will appear here once you've set one up."
                : "Your running campaigns will appear here."}
            </p>
          </Panel>
        ) : (
          <div className="grid gap-6">
            {cards.map(({ campaign, areas, live, performance }) => {
              const positions =
                live.available && live.data.campaign_id === campaign.id
                  ? live.data.positions
                  : null;
              const base = `/advertiser/campaigns/${campaign.id}`;
              return (
                <Panel key={campaign.id} className="portal-card overflow-hidden">
                  <div className="campaign-card-visuals">
                    <div>
                      <CampaignArtwork name={campaign.name} fileId={campaign.preview_file_id} />
                      <span className="border-edge border-t bg-white px-3 py-2 text-sm font-semibold">
                        Your advert
                      </span>
                    </div>
                    <div className="border-edge relative sm:border-l">
                      <div className="relative min-h-48 flex-1">
                        {areas.available ? (
                          <CampaignMap
                            areas={areas.data.items.map(({ id, name, geometry, zone_type }) => ({
                              id,
                              name,
                              geometry,
                              zone_type,
                            }))}
                            positions={positions ?? []}
                          />
                        ) : (
                          <p className="text-muted p-5">Campaign areas couldn&apos;t be loaded.</p>
                        )}
                      </div>
                      {positions !== null && positions.length > 0 ? (
                        <a
                          href="/advertiser"
                          className="text-green border-edge border-t bg-white px-3 py-2 text-right text-sm font-semibold"
                        >
                          Refresh
                        </a>
                      ) : null}
                      {positions !== null && positions.length === 0 ? (
                        <p className="text-muted border-edge border-t bg-white p-2 text-center text-sm">
                          No cars driving right now
                        </p>
                      ) : null}
                      {positions === null ? (
                        <p className="text-muted border-edge border-t bg-white p-2 text-center text-sm">
                          Driving positions couldn&apos;t be loaded.{" "}
                          <a href="/advertiser" className="text-green font-semibold">
                            Try again
                          </a>
                        </p>
                      ) : null}
                    </div>
                  </div>
                  <div className="border-edge flex flex-wrap items-center justify-between gap-4 border-b p-5 md:px-6">
                    <div>
                      <p className="text-green mb-2 flex items-center gap-2 text-sm font-semibold">
                        <span className="bg-green size-2 rounded-full" />
                        Running
                      </p>
                      <h3 className="font-display text-lg font-semibold">
                        <Link href={base} className="hover:text-green">
                          {campaign.name}
                        </Link>
                      </h3>
                      <div className="text-muted mt-2 flex flex-wrap items-center gap-x-4 gap-y-2 text-sm">
                        <span className="inline-flex items-center gap-2">
                          <PortalIcon name="calendar" className="size-4" />
                          {formatDateRange(campaign.start_at, campaign.end_at)}
                        </span>
                        {areas.available && areas.data.items.length ? (
                          <span className="inline-flex items-center gap-2">
                            <PortalIcon name="pin" className="size-4" />
                            {areas.data.items.map((area) => area.name).join(", ")}
                          </span>
                        ) : null}
                        <span className="inline-flex items-center gap-2">
                          <PortalIcon name="car" className="size-4" />
                          {positions === null
                            ? "Cars unavailable"
                            : `${positions.length} ${positions.length === 1 ? "car" : "cars"}`}
                        </span>
                      </div>
                      <p className="text-green mt-2 text-sm font-semibold">
                        {campaignDay(campaign.start_at, campaign.end_at)}
                      </p>
                    </div>
                    <Link href={base} className="brand-secondary">
                      View campaign →
                    </Link>
                  </div>
                  <PerformanceCard {...performance} cars={positions?.length ?? null} compact />
                </Panel>
              );
            })}
          </div>
        )}
      </section>
    </div>
  );
}
