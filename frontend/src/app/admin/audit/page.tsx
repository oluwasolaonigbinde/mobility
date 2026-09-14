import type { Metadata } from "next";
import Link from "next/link";
import { createApiClient } from "@/lib/api/client";
import { getSessionToken } from "@/lib/auth/session";
import { Field } from "@/components/ui/field";
import { PageHeader } from "@/components/ui/page-header";
import { Pagination } from "@/components/ui/pagination";
import { Panel } from "@/components/ui/panel";

export const metadata: Metadata = { title: "Audit trail" };
const PAGE_SIZE = 50;

function href(params: { action?: string; entity_type?: string; offset?: number }): string {
  const query = new URLSearchParams();
  if (params.action) query.set("action", params.action);
  if (params.entity_type) query.set("entity_type", params.entity_type);
  if (params.offset) query.set("offset", String(params.offset));
  return query.size ? `/admin/audit?${query.toString()}` : "/admin/audit";
}

export default async function AdminAuditPage({
  searchParams,
}: {
  searchParams: Promise<{ action?: string; entity_type?: string; offset?: string }>;
}) {
  const params = await searchParams;
  const rawOffset = Number(params.offset ?? 0);
  const offset = Number.isFinite(rawOffset) && rawOffset > 0 ? Math.floor(rawOffset) : 0;
  const api = createApiClient(await getSessionToken());
  const { data } = await api.GET("/api/v1/admin/audit-events", {
    params: {
      query: {
        limit: PAGE_SIZE,
        offset,
        ...(params.action ? { action: params.action } : {}),
        ...(params.entity_type ? { entity_type: params.entity_type } : {}),
      },
    },
  });
  const items = data?.items ?? [];
  const total = data?.total ?? 0;
  const activeFilters = [
    params.action ? `action “${params.action}”` : undefined,
    params.entity_type ? `entity type “${params.entity_type}”` : undefined,
  ].filter(Boolean);

  return (
    <div className="animate-rise mx-auto max-w-6xl">
      <PageHeader
        title="Audit trail"
        eyebrow={`${total} recorded event${total === 1 ? "" : "s"}`}
      />
      <form className="mb-4 grid gap-3 sm:grid-cols-[1fr_1fr_auto] sm:items-end">
        <Field
          label="Action"
          name="action"
          defaultValue={params.action}
          placeholder="Action, e.g. auth.login.succeeded"
          aria-describedby="audit-filter-hint"
        />
        <Field
          label="Entity type"
          name="entity_type"
          defaultValue={params.entity_type}
          placeholder="Entity type"
          aria-describedby="audit-filter-hint"
        />
        <button className="bg-amber text-bg h-11 rounded-lg px-5 text-sm font-medium">
          Filter
        </button>
        <p id="audit-filter-hint" className="micro text-faint sm:col-span-3">
          Each filter matches an exact action or entity type as shown in the table. Leave a field
          empty to include every value.
        </p>
      </form>
      {(params.action || params.entity_type) && (
        <Link href="/admin/audit" className="text-amber mb-4 inline-block text-sm">
          Clear filters
        </Link>
      )}
      <Panel className="overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full min-w-[850px] text-sm">
            <thead>
              <tr className="border-edge text-muted border-b text-left">
                <th className="px-5 py-3 font-normal">When</th>
                <th className="px-5 py-3 font-normal">Actor</th>
                <th className="px-5 py-3 font-normal">Action</th>
                <th className="px-5 py-3 font-normal">Entity</th>
                <th className="px-5 py-3 font-normal">Details</th>
              </tr>
            </thead>
            <tbody>
              {items.map((event) => (
                <tr key={event.id} className="border-edge/60 border-b align-top last:border-0">
                  <td className="px-5 py-3 whitespace-nowrap">
                    {new Date(event.created_at).toLocaleString("en-NG")}
                  </td>
                  <td className="px-5 py-3">{event.actor_email ?? "System"}</td>
                  <td className="px-5 py-3 font-mono text-xs">{event.action}</td>
                  <td className="px-5 py-3">
                    <p>{event.entity_type}</p>
                    {event.entity_id ? (
                      <p className="text-faint font-mono text-xs">{event.entity_id}</p>
                    ) : null}
                  </td>
                  <td className="px-5 py-3">
                    <details>
                      <summary className="text-amber cursor-pointer">View</summary>
                      <pre className="bg-bg mt-2 max-w-sm overflow-auto rounded p-2 text-xs">
                        {JSON.stringify(event.metadata, null, 2)}
                      </pre>
                    </details>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {items.length === 0 ? (
          <p className="text-muted p-8 text-center">
            {activeFilters.length
              ? "No events exactly match these filters."
              : "No matching events."}
          </p>
        ) : null}
      </Panel>
      {activeFilters.length ? (
        <p className="micro text-faint mt-3">Showing events with {activeFilters.join(" and ")}.</p>
      ) : null}
      <Pagination
        total={total}
        limit={PAGE_SIZE}
        offset={offset}
        hrefFor={(value) =>
          href({ action: params.action, entity_type: params.entity_type, offset: value })
        }
      />
    </div>
  );
}
