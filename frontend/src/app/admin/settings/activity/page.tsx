import { adminValueFailure } from "@/lib/api/admin-read";
import type { Metadata } from "next";
import Link from "next/link";
import { createApiClient } from "@/lib/api/client";
import { getSessionToken } from "@/lib/auth/session";
import { PageHeader } from "@/components/ui/page-header";
import { Pagination } from "@/components/ui/pagination";
import { QueueUnavailable } from "../../queue-search";
import { adminActivity, activityFilterOptions } from "@/lib/status/admin";
import { formatDateTime } from "@/lib/format";
import { Panel } from "@/components/ui/panel";

export const metadata: Metadata = { title: "Activity log" };
const PAGE_SIZE = 50;
const recordOptions: Record<string, string> = {
  campaign: "Campaigns",
  driver_profile: "Drivers",
  organization: "Advertisers",
  user: "Accounts",
  stored_file: "Files",
  trip_session: "Trips",
  complaint: "Messages and requests",
};

function href(params: { action?: string; entity_type?: string; offset?: number }): string {
  const query = new URLSearchParams();
  if (params.action) query.set("action", params.action);
  if (params.entity_type) query.set("entity_type", params.entity_type);
  if (params.offset) query.set("offset", String(params.offset));
  return query.size ? `/admin/settings/activity?${query.toString()}` : "/admin/settings/activity";
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
  let result;
  try {
    result = await api.GET("/api/v1/admin/audit-events", {
      params: {
        query: {
          limit: PAGE_SIZE,
          offset,
          ...(params.action ? { action: params.action } : {}),
          ...(params.entity_type ? { entity_type: params.entity_type } : {}),
        },
      },
    });
  } catch (error) {
    adminValueFailure(error);
    return <QueueUnavailable />;
  }
  const { data } = result;
  if (!data) return <QueueUnavailable />;
  const items = data.items;
  const total = data.total;
  const activeFilters = [
    params.action ? adminActivity(params.action) : undefined,
    params.entity_type ? (recordOptions[params.entity_type] ?? "Selected records") : undefined,
  ].filter(Boolean);

  return (
    <div className="animate-rise mx-auto max-w-6xl">
      <PageHeader
        title="Activity log"
        eyebrow={`${total} recorded event${total === 1 ? "" : "s"}`}
      />
      <form className="mb-4 grid gap-3 sm:grid-cols-[1fr_1fr_auto] sm:items-end">
        <label className="flex flex-col gap-2 text-sm">
          Activity
          <select
            name="action"
            defaultValue={params.action ?? ""}
            className="border-edge bg-raised h-11 rounded-lg border px-3"
          >
            <option value="">All activity</option>
            {params.action &&
            !activityFilterOptions.some((option) => option.value === params.action) ? (
              <option value={params.action}>{adminActivity(params.action)}</option>
            ) : null}
            {activityFilterOptions.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-2 text-sm">
          About
          <select
            name="entity_type"
            defaultValue={params.entity_type ?? ""}
            className="border-edge bg-raised h-11 rounded-lg border px-3"
          >
            <option value="">All records</option>
            {params.entity_type && !recordOptions[params.entity_type] ? (
              <option value={params.entity_type}>Selected records</option>
            ) : null}
            {Object.entries(recordOptions).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </label>
        <button className="bg-amber text-bg h-11 rounded-lg px-5 text-sm font-medium">
          Filter
        </button>
      </form>
      {(params.action || params.entity_type) && (
        <Link href="/admin/settings/activity" className="text-amber mb-4 inline-block text-sm">
          Clear filters
        </Link>
      )}
      <Panel className="overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-edge text-muted border-b text-left">
                <th className="px-5 py-3 font-normal">When</th>
                <th className="px-5 py-3 font-normal">Actor</th>
                <th className="px-5 py-3 font-normal">Action</th>
              </tr>
            </thead>
            <tbody>
              {items.map((event) => (
                <tr key={event.id} className="border-edge/60 border-b align-top last:border-0">
                  <td className="px-5 py-3 whitespace-nowrap">
                    {formatDateTime(event.created_at)}
                  </td>
                  <td className="px-5 py-3">{event.actor_email ?? "System"}</td>
                  <td className="px-5 py-3">{adminActivity(event.action)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {items.length === 0 ? (
          <p className="text-muted p-8 text-center">
            {activeFilters.length ? "No activity matches these filters." : "No matching events."}
          </p>
        ) : null}
      </Panel>
      {activeFilters.length ? (
        <p className="text-muted mt-3 text-sm">Showing: {activeFilters.join(" · ")}.</p>
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
