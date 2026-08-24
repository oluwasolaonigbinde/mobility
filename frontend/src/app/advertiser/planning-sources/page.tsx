import type { Metadata } from "next";
import { createApiClient } from "@/lib/api/client";
import { getSessionToken } from "@/lib/auth/session";
import { formatDate } from "@/lib/format";
import { EmptyState } from "@/components/ui/empty-state";
import { PageHeader } from "@/components/ui/page-header";
import { Panel } from "@/components/ui/panel";
import { StatusChip } from "@/components/ui/status-chip";
import { deactivateSourceAction } from "./actions";
import { SourceForm } from "./source-form";

export const metadata: Metadata = { title: "Planning sources" };

export default async function PlanningSourcesPage() {
  const api = createApiClient(await getSessionToken());
  const { data } = await api.GET("/api/v1/advertiser/retargeting-sources");
  const items = data?.items ?? [];
  return (
    <div className="animate-rise mx-auto max-w-6xl">
      <PageHeader title="Planning sources" eyebrow="Aggregate-only retargeting inputs" />
      <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_22rem]">
        <div>
          {items.length === 0 ? (
            <EmptyState
              title="No planning sources"
              body="Record an allowlisted aggregate source to begin planning."
            />
          ) : (
            <Panel className="overflow-hidden">
              <div className="divide-edge divide-y">
                {items.map((source) => (
                  <article key={source.id} className="p-5">
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <div>
                        <div className="flex items-center gap-2">
                          <h2 className="font-medium">{source.source_type}</h2>
                          <StatusChip
                            tone={
                              source.status === "active"
                                ? "green"
                                : source.status === "expired"
                                  ? "amber"
                                  : "default"
                            }
                          >
                            {source.status}
                          </StatusChip>
                        </div>
                        <p className="micro text-faint mt-2">
                          Expires {formatDate(source.expires_at)}
                        </p>
                        <p className="micro text-faint mt-1 font-mono">
                          Evidence {source.snapshot_sha256}
                        </p>
                      </div>
                      {source.status === "active" ? (
                        <form action={deactivateSourceAction.bind(null, source.id)}>
                          <button className="border-edge hover:border-coral rounded-lg border px-3 py-2 text-sm">
                            Deactivate
                          </button>
                        </form>
                      ) : null}
                    </div>
                  </article>
                ))}
              </div>
            </Panel>
          )}
        </div>
        <Panel className="h-fit p-5">
          <h2 className="mb-4 font-medium">Record aggregate source</h2>
          <SourceForm />
        </Panel>
      </div>
    </div>
  );
}
