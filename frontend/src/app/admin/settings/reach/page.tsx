import Link from "next/link";
import { createApiClient } from "@/lib/api/client";
import { getSessionToken } from "@/lib/auth/session";
import { PageHeader } from "@/components/ui/page-header";
import { Panel } from "@/components/ui/panel";
import { Pagination } from "@/components/ui/pagination";
import { QueueUnavailable } from "../../queue-search";
import { ProfileForm } from "../../traffic/profile-form";
export default async function ReachEstimates({
  searchParams,
}: {
  searchParams: Promise<{ profile?: string; offset?: string }>;
}) {
  const query = await searchParams,
    raw = Number(query.offset ?? 0),
    offset = Number.isFinite(raw) ? Math.max(0, Math.floor(raw)) : 0;
  const api = createApiClient(await getSessionToken());
  const { data } = await api
    .GET("/api/v1/admin/traffic-density-profiles", {
      params: { query: { limit: 50, offset, status: "active" } },
    })
    .catch(() => ({ data: undefined }));
  let selected = data?.items.find((profile) => profile.id === query.profile),
    selectionFailed = false;
  if (query.profile && query.profile !== "new" && !selected) {
    const { data: detail } = await api
      .GET("/api/v1/admin/traffic-density-profiles/{profile_id}", {
        params: { path: { profile_id: query.profile } },
      })
      .catch(() => ({ data: undefined }));
    if (detail?.id === query.profile) selected = detail;
    else selectionFailed = true;
  }
  const editing =
    query.profile === "new"
      ? null
      : (selected ?? data?.items.find((profile) => profile.is_default) ?? data?.items[0] ?? null);
  const href = (next: number) =>
    `/admin/settings/reach?${new URLSearchParams({ ...query, offset: String(next) })}`;
  return (
    <div className="mx-auto max-w-4xl space-y-5">
      <PageHeader
        title="Reach estimates"
        eyebrow="Traffic, stopping time and time-of-day values used to estimate advertising reach"
      />
      {!data || selectionFailed ? (
        <QueueUnavailable />
      ) : (
        <>
          <nav aria-label="Reach estimates" className="flex flex-wrap gap-3">
            {data.items.map((profile) => (
              <Link
                className="border-edge rounded border px-3 py-2"
                key={profile.id}
                href={`/admin/settings/reach?${new URLSearchParams({ offset: String(offset), profile: profile.id })}`}
              >
                {profile.name} · version {profile.revision}
                {profile.is_default ? " · Default" : ""}
              </Link>
            ))}
            <Link
              className="border-edge rounded border px-3 py-2"
              href={`/admin/settings/reach?${new URLSearchParams({ offset: String(offset), profile: "new" })}`}
            >
              New reach estimate
            </Link>
          </nav>
          <Panel className="p-6">
            <h2 className="mb-4">{editing ? editing.name : "New reach estimate"}</h2>
            <ProfileForm profile={editing} />
          </Panel>
          {!data.items.length ? <p>No reach estimates recorded.</p> : null}
          <Pagination total={data.total} limit={50} offset={offset} hrefFor={href} />
        </>
      )}
    </div>
  );
}
