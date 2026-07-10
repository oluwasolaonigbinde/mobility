import type { Metadata } from "next";
import { createApiClient } from "@/lib/api/client";
import { getSessionToken } from "@/lib/auth/session";
import { PageHeader } from "@/components/ui/page-header";
import { Panel } from "@/components/ui/panel";
import { StatusChip } from "@/components/ui/status-chip";
import { ProfileForm } from "./profile-form";
import { cx } from "@/lib/cx";

export const metadata: Metadata = { title: "Traffic profiles" };

export default async function TrafficProfilesPage({
  searchParams,
}: {
  searchParams: Promise<{ profile?: string }>;
}) {
  const params = await searchParams;
  const api = createApiClient(await getSessionToken());
  const { data } = await api.GET("/api/v1/admin/traffic-density-profiles", {
    params: { query: { limit: 50 } },
  });
  const items = data?.items ?? [];
  const editing =
    params.profile === "new"
      ? null
      : (items.find((p) => p.id === params.profile) ??
        items.find((p) => p.is_default) ??
        items[0] ??
        null);

  return (
    <div className="animate-rise mx-auto max-w-4xl">
      <PageHeader
        title="Traffic profiles"
        eyebrow="The analytics engine's assumptions — density, dwell and time-of-day weights behind every impression estimate"
      />

      <div className="mb-5 flex gap-1 overflow-x-auto" role="group" aria-label="Profiles">
        {items.map((p) => (
          <a
            key={p.id}
            href={`/admin/traffic?profile=${p.id}`}
            className={cx(
              "micro rounded-lg px-3 py-2 whitespace-nowrap transition-colors",
              editing?.id === p.id ? "bg-raised text-amber" : "text-muted hover:text-ink",
            )}
          >
            {p.name}
            {p.is_default ? " ★" : ""}
          </a>
        ))}
        <a
          href="/admin/traffic?profile=new"
          className={cx(
            "micro rounded-lg px-3 py-2 whitespace-nowrap transition-colors",
            editing === null ? "bg-raised text-amber" : "text-muted hover:text-ink",
          )}
        >
          + New profile
        </a>
      </div>

      <Panel className="p-6 md:p-8">
        <div className="mb-5 flex items-center justify-between">
          <h2 className="micro text-muted">
            {editing ? `Editing "${editing.name}"` : "New profile"}
          </h2>
          {editing?.is_default ? <StatusChip tone="amber">default</StatusChip> : null}
        </div>
        <ProfileForm profile={editing} />
      </Panel>

      {items.length === 0 ? (
        <p className="micro text-faint mt-4">
          No profiles yet — the engine uses built-in defaults until one is created.
        </p>
      ) : null}
    </div>
  );
}
