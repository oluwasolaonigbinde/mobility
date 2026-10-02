import Link from "next/link";
import { createApiClient } from "@/lib/api/client";
import { getSessionToken } from "@/lib/auth/session";
import { adminStatus } from "@/lib/status/admin";
import { formatDateRange, formatMoneyExact } from "@/lib/format";
import { PageHeader } from "@/components/ui/page-header";
import { Pagination } from "@/components/ui/pagination";
import { QueueSearch, QueueUnavailable } from "../queue-search";
import type { components } from "@/lib/api/schema";

type Campaign = components["schemas"]["AdminCampaignRead"];
const tabs = [
  {
    id: "needs-review",
    title: "For review",
    statuses: ["pending_review"],
    sources: [
      { id: "pending_review", title: "Campaign details" },
      { id: "artwork", title: "Artwork" },
      { id: "installation", title: "Installation photos" },
      { id: "changes", title: "Change requests" },
    ],
  },
  {
    id: "getting-ready",
    title: "Getting ready",
    statuses: ["draft", "approved", "scheduled"],
    sources: [
      { id: "draft", title: "Draft" },
      { id: "approved", title: "Approved" },
      { id: "scheduled", title: "Scheduled" },
    ],
  },
  {
    id: "live",
    title: "Live",
    statuses: ["active", "paused"],
    sources: [
      { id: "active", title: "Live" },
      { id: "paused", title: "Paused" },
    ],
  },
  {
    id: "ended",
    title: "Ended",
    statuses: ["completed", "cancelled", "rejected"],
    sources: [
      { id: "completed", title: "Completed" },
      { id: "cancelled", title: "Cancelled" },
      { id: "rejected", title: "Not approved" },
    ],
  },
];
export default async function CampaignsPage({
  searchParams,
}: {
  searchParams: Promise<{
    tab?: string;
    source?: string;
    q?: string;
    offset?: string;
    section?: string;
    [key: string]: string | undefined;
  }>;
}) {
  const p = await searchParams;
  const tab = tabs.find((t) => t.id === p.tab) ?? tabs[0]!;
  if (tab.sources.some((s) => s.id === p.source)) return CampaignList({ searchParams });
  const lists = await Promise.all(
    tab.sources.map(async (source) => ({
      source,
      body: await CampaignList(
        {
          searchParams: Promise.resolve({
            ...p,
            source: source.id,
            offset: p[source.id + "_offset"],
          }),
        },
        true,
      ),
    })),
  );
  return (
    <div className="mx-auto max-w-6xl">
      <PageHeader title="Campaigns" />
      <nav aria-label="Campaign status" className="mb-4 flex gap-2 overflow-x-auto">
        {tabs.map((t) => (
          <Link
            key={t.id}
            href={`/admin/campaigns?tab=${t.id}`}
            aria-current={t.id === tab.id ? "page" : undefined}
            className="rounded-lg px-4 py-2 text-sm whitespace-nowrap"
          >
            {t.title}
          </Link>
        ))}
      </nav>
      <div className="space-y-8">
        {lists.map(({ source, body }) => (
          <section key={source.id} aria-label={source.title}>
            <h2 className="mb-3 text-lg font-medium">{source.title}</h2>
            {body}
          </section>
        ))}
      </div>
    </div>
  );
}
async function CampaignList(
  { searchParams }: { searchParams: Promise<Record<string, string | undefined>> },
  embedded = false,
) {
  const p = await searchParams;
  const tab = tabs.find((t) => t.id === p.tab) ?? tabs[0]!;
  const source = tab.sources.find((s) => s.id === p.source) ?? tab.sources[0]!;
  const offset = Number.isFinite(Number(p.offset)) ? Math.max(0, Math.floor(Number(p.offset))) : 0;
  const api = createApiClient(await getSessionToken());
  let items:
    { key: string; campaign: Campaign; next: string; section: string; job?: string }[] | undefined;
  let total: number | undefined;
  if (source.id === "artwork") {
    const { data } = await api
      .GET("/api/v1/admin/creatives/pending-review", { params: { query: { limit: 25, offset } } })
      .catch(() => ({ data: undefined }));
    total = data?.total;
    if (data) {
      const parents = await Promise.all(
        data.items.map((row) =>
          api
            .GET("/api/v1/admin/campaigns/{campaign_id}", {
              params: { path: { campaign_id: row.creative.campaign_id } },
            })
            .catch(() => ({ data: undefined })),
        ),
      );
      if (parents.every((parent) => parent.data))
        items = data.items.map((row, i) => ({
          key: row.creative.id,
          campaign: parents[i]!.data!,
          next: `Review artwork: ${row.creative.name}`,
          section: "artwork",
        }));
    }
  } else if (source.id === "installation") {
    const { data } = await api
      .GET("/api/v1/admin/installation-evidence/pending")
      .catch(() => ({ data: undefined }));
    if (data) {
      total = data.items.length;
      const selected = data.items.slice(offset, offset + 25);
      const parents = await Promise.all(
        selected.map(async (evidence) => {
          const job = (
            await api
              .GET("/api/v1/admin/campaign-assignments/{assignment_id}", {
                params: { path: { assignment_id: evidence.assignment_id } },
              })
              .catch(() => ({ data: undefined }))
          ).data;
          if (!job || job.vehicle_id !== evidence.vehicle_id) return undefined;
          const campaign = (
            await api
              .GET("/api/v1/admin/campaigns/{campaign_id}", {
                params: { path: { campaign_id: job.campaign_id } },
              })
              .catch(() => ({ data: undefined }))
          ).data;
          return campaign
            ? {
                key: evidence.id,
                campaign,
                next: `Review installation photos: ${job.driver_profile?.full_name ?? "Driver"} · ${job.vehicle?.plate_number ?? "No car recorded"}`,
                section: "drivers",
                job: job.id,
              }
            : undefined;
        }),
      );
      if (parents.every((parent) => parent !== undefined)) items = parents;
    }
  } else if (source.id === "changes") {
    const { data } = await api
      .GET("/api/v1/admin/campaign-change-requests/pending")
      .catch(() => ({ data: undefined }));
    if (data) {
      total = data.items.length;
      const selected = data.items.slice(offset, offset + 25);
      const parents = await Promise.all(
        selected.map((row) =>
          api
            .GET("/api/v1/admin/campaigns/{campaign_id}", {
              params: { path: { campaign_id: row.campaign_id } },
            })
            .catch(() => ({ data: undefined })),
        ),
      );
      if (parents.every((parent) => parent.data))
        items = selected.map((row, i) => ({
          key: row.id,
          campaign: parents[i]!.data!,
          next: "Review change request",
          section: "overview",
        }));
    }
  } else {
    const { data } = await api
      .GET("/api/v1/admin/campaigns", {
        params: { query: { status: source.id as Campaign["status"], q: p.q, limit: 25, offset } },
      })
      .catch(() => ({ data: undefined }));
    items = data?.items.map((campaign) => ({
      key: campaign.id,
      campaign,
      next:
        source.id === "pending_review"
          ? "Review campaign details"
          : source.id === "paused"
            ? "Review pause and funding"
            : "View launch checklist",
      section: p.section ?? "overview",
    }));
    total = data?.total;
  }
  const summaries = items
    ? await Promise.all(
        items.map(async ({ campaign }) => ({
          jobs: (
            await api
              .GET("/api/v1/admin/campaign-assignments", {
                params: { query: { campaign_id: campaign.id, limit: 1 } },
              })
              .catch(() => ({ data: undefined }))
          ).data,
          commercial: (
            await api
              .GET("/api/v1/admin/campaigns/{campaign_id}/commercial", {
                params: { path: { campaign_id: campaign.id } },
              })
              .catch(() => ({ data: undefined }))
          ).data,
        })),
      )
    : [];
  return (
    <div className="mx-auto max-w-6xl">
      {!embedded ? (
        <>
          <PageHeader title="Campaigns" />
          <nav aria-label="Campaign status" className="mb-4 flex gap-2 overflow-x-auto">
            {tabs.map((t) => (
              <Link
                key={t.id}
                href={`/admin/campaigns?tab=${t.id}`}
                aria-current={t.id === tab.id ? "page" : undefined}
                className={`rounded-lg px-4 py-2 text-sm whitespace-nowrap ${t.id === tab.id ? "bg-raised text-amber" : "text-muted"}`}
              >
                {t.title}
              </Link>
            ))}
          </nav>
          <nav aria-label="Campaign source" className="mb-5 flex flex-wrap gap-4 text-sm">
            {tab.sources.map((s) => (
              <Link
                key={s.id}
                href={`/admin/campaigns?tab=${tab.id}&source=${s.id}`}
                aria-current={s.id === source.id ? "page" : undefined}
                className={s.id === source.id ? "text-amber underline" : "text-cyan underline"}
              >
                {s.title}
              </Link>
            ))}
          </nav>
        </>
      ) : null}
      {!["artwork", "changes", "installation"].includes(source.id) ? (
        <QueueSearch q={p.q} label="Search campaigns">
          <input type="hidden" name="tab" value={tab.id} />
          <input type="hidden" name="source" value={source.id} />
        </QueueSearch>
      ) : null}
      {!items || summaries.some((summary) => !summary.jobs || !summary.commercial) ? (
        <QueueUnavailable />
      ) : (
        <>
          <p className="text-muted mb-4 text-sm">
            {total} matching{" "}
            {source.id === "artwork"
              ? "artwork submissions"
              : source.id === "changes"
                ? "change requests"
                : source.id === "installation"
                  ? "installation submissions"
                  : "campaigns"}
          </p>
          {!items.length ? (
            <p>Nothing in this list. Choose another status or change the search.</p>
          ) : (
            <div className="grid gap-3">
              {items.map(({ key, campaign, next, section, job }, i) => {
                const evaluation = summaries[i]?.commercial?.budget_evaluations.at(-1);
                const spent = evaluation?.billing_spend_amount;
                const percentage =
                  spent != null &&
                  campaign.budget_amount != null &&
                  Number(campaign.budget_amount) > 0
                    ? Math.min(
                        100,
                        Math.max(0, (Number(spent) / Number(campaign.budget_amount)) * 100),
                      )
                    : undefined;
                return (
                  <Link
                    key={key}
                    href={`/admin/campaigns/${campaign.id}${job ? `?job=${job}` : ""}#${section}`}
                    className="border-edge hover:bg-raised grid gap-3 rounded-xl border p-4 md:grid-cols-[2fr_1fr_1.5fr]"
                  >
                    <div>
                      <h2 className="font-medium">{campaign.name}</h2>
                      <p className="text-muted text-sm">{campaign.organization.name}</p>
                      <p className="text-muted mt-1 text-sm">
                        {formatDateRange(campaign.start_at, campaign.end_at)}
                      </p>
                    </div>
                    <div>
                      <p className="text-sm">{adminStatus(campaign.status, "campaign")}</p>
                      <p className="text-muted mt-1 text-sm">
                        {summaries[i]?.jobs
                          ? `${summaries[i]!.jobs!.total} driver jobs`
                          : "No jobs recorded"}
                      </p>
                    </div>
                    <div>
                      {percentage !== undefined ? (
                        <>
                          <p className="text-muted text-xs">
                            Budget used: {formatMoneyExact(spent, campaign.currency)}
                          </p>
                          <progress
                            aria-label={`Budget used for ${campaign.name}`}
                            max={100}
                            value={percentage}
                            className="my-2 h-2 w-full"
                          />
                        </>
                      ) : null}
                      <p className="text-sm">Next: {next}</p>
                    </div>
                  </Link>
                );
              })}
            </div>
          )}
          <Pagination
            total={total ?? 0}
            limit={25}
            offset={offset}
            hrefFor={(n) =>
              `/admin/campaigns?${new URLSearchParams(embedded ? { ...(Object.fromEntries(Object.entries(p).filter(([key, value]) => key !== "source" && key !== "offset" && value !== undefined)) as Record<string, string>), tab: tab.id, [source.id + "_offset"]: String(n) } : { tab: tab.id, source: source.id, q: p.q ?? "", offset: String(n) })}`
            }
          />
        </>
      )}
    </div>
  );
}
