import { cache } from "react";
import { headers } from "next/headers";
import { createApiClient, type ApiClient } from "@/lib/api/client";
import { getSessionToken } from "@/lib/auth/session";
import { formatDate, formatMoneyExact } from "@/lib/format";
import { CATEGORY_LABELS } from "@/lib/complaints/labels";

export const departments = [
  "Operations",
  "Compliance",
  "Finance",
  "Customer Service",
  "Admin",
] as const;
export type Department = (typeof departments)[number];
type Area = "drivers" | "campaigns" | "trips" | "money" | "support";
export type QueueTask = {
  key: string;
  area: Area;
  at: string;
  event: string;
  describe: () => Promise<{ name: string; reason: string; href: string }>;
};
type QueueRows = QueueTask[] & { total?: number; counts?: Partial<Record<Area, number>> };
export type QueueCollections = Record<Department, QueueRows | undefined>;
type Source = {
  id: string;
  department: Department;
  area: Area;
  title: string;
  href: string;
  read: (
    api: ApiClient,
    limit: number,
    offset: number,
  ) => Promise<{ items: QueueTask[]; total: number } | undefined>;
};
function present(value: string | null | undefined) {
  if (!value?.trim()) throw new Error("Incomplete queue context");
  return value;
}
function task(
  key: string,
  area: Area,
  at: string | null | undefined,
  event: string,
  name: string,
  reason: string,
  href: string,
): QueueTask {
  if (!at || !Number.isFinite(Date.parse(at))) throw new Error("Incomplete queue date");
  return { key, area, at, event, describe: async () => ({ name: present(name), reason, href }) };
}
function source<T extends { id: string }>(
  id: string,
  department: Department,
  area: Area,
  title: string,
  href: string,
  read: (
    api: ApiClient,
    limit: number,
    offset: number,
  ) => Promise<{ data?: { items: T[]; total?: number | null } }>,
  project: (row: T) => QueueTask,
): Source {
  return {
    id,
    department,
    area,
    title,
    href,
    read: async (api, limit, offset) => {
      try {
        const { data } = await read(api, limit, offset);
        if (
          !data ||
          !Number.isInteger(data.total) ||
          data.total! < 0 ||
          data.items.length > limit ||
          new Set(data.items.map((row) => row.id)).size !== data.items.length
        )
          return undefined;
        return { items: data.items.map(project), total: data.total! };
      } catch {
        return undefined;
      }
    },
  };
}
export const sources: Source[] = [
  source(
    "applications",
    "Operations",
    "drivers",
    "Applications",
    "/admin/drivers?tab=applicants",
    (api, limit, offset) =>
      api.GET("/api/v1/admin/driver-applications", {
        params: { query: { limit, offset, oldest_first: true } },
      }),
    (r) =>
      task(
        `application:${r.id}`,
        "drivers",
        r.created_at,
        "Created",
        r.full_name,
        "New application",
        `/admin/drivers/${r.driver_profile_id}?application=${r.id}#checklist`,
      ),
  ),
  source(
    "cars",
    "Operations",
    "drivers",
    "Cars to approve",
    "/admin/drivers?source=cars",
    (api, limit, offset) =>
      api.GET("/api/v1/admin/vehicles", {
        params: { query: { limit, offset, status: "pending", oldest_first: true } },
      }),
    (r) =>
      task(
        `vehicle:${r.id}`,
        "drivers",
        r.created_at,
        "Created",
        `${present(r.driver_profile.full_name)} · ${present(r.plate_number)}`,
        "Car to approve",
        `/admin/drivers/${r.driver_profile_id}#cars`,
      ),
  ),
  source(
    "jobs",
    "Operations",
    "campaigns",
    "Accepted jobs",
    "/admin/campaigns?tab=live",
    (api, limit, offset) =>
      api.GET("/api/v1/admin/campaign-assignments", {
        params: { query: { limit, offset, status: "accepted", oldest_first: true } },
      }),
    (r) =>
      task(
        `job:${r.id}`,
        "campaigns",
        r.accepted_at,
        "Accepted",
        `${present(r.driver_profile?.full_name)} · ${present(r.vehicle?.plate_number)}`,
        `Accepted job waiting to start on ${present(r.campaign?.name)}`,
        `/admin/campaigns/${r.campaign_id}?drawer=job&job=${r.id}#drivers`,
      ),
  ),
  source(
    "trips",
    "Operations",
    "trips",
    "Suspicious trips",
    "/admin/trip-checks",
    (api, limit, offset) =>
      api.GET("/api/v1/admin/fraud-flags", {
        params: {
          query: { limit, offset, unresolved_only: true, group_by_trip: true, oldest_first: true },
        },
      }),
    (r) =>
      task(
        `trip:${r.trip_session_id}`,
        "trips",
        r.detected_at,
        "Detected",
        present(r.driver_name),
        `Trip on ${formatDate(r.trip_started_at)}: ${r.problem_count} ${r.problem_count === 1 ? "problem" : "problems"} · ${r.money_effect.held_currency ? `${formatMoneyExact(r.money_effect.held_pending_net, r.money_effect.held_currency)} held` : "no pay held"}`,
        `/admin/trip-checks?flag=${r.id}`,
      ),
  ),
  source(
    "late",
    "Operations",
    "trips",
    "Late uploads",
    "/admin/trip-checks?tab=late",
    (api, limit, offset) =>
      api.GET("/api/v1/admin/trips/quarantined-batches", {
        params: { query: { limit, offset, status: "quarantined" } },
      }),
    (r) =>
      task(
        `late:${r.id}`,
        "trips",
        r.received_at,
        "Received",
        `${present(r.driver_name)} · ${present(r.vehicle_plate)}`,
        `Late upload for ${formatDate(r.trip_started_at)} trip`,
        `/admin/trip-checks?tab=late&late=${r.id}`,
      ),
  ),
  source(
    "campaigns",
    "Compliance",
    "campaigns",
    "Campaigns for review",
    "/admin/campaigns?tab=for-review",
    (api, limit, offset) =>
      api.GET("/api/v1/admin/campaigns/pending-review", {
        params: { query: { limit, offset, oldest_first: true } },
      }),
    (r) =>
      task(
        `campaign:${r.id}`,
        "campaigns",
        r.created_at,
        "Created",
        r.name,
        "Campaign for review",
        `/admin/campaigns/${r.id}#overview`,
      ),
  ),
  source(
    "artwork",
    "Compliance",
    "campaigns",
    "Artwork for review",
    "/admin/campaigns?tab=for-review&source=artwork",
    (api, limit, offset) =>
      api
        .GET("/api/v1/admin/creatives/pending-review", { params: { query: { limit, offset } } })
        .then(({ data }) => ({
          data: data
            ? { ...data, items: data.items.map((r) => ({ ...r, id: r.creative.id })) }
            : undefined,
        })),
    (r) =>
      task(
        `artwork:${r.id}`,
        "campaigns",
        r.creative.created_at,
        "Created",
        r.campaign_name,
        `Artwork for review · ${r.creative.name}`,
        `/admin/campaigns/${r.creative.campaign_id}#artwork`,
      ),
  ),
  source(
    "photos",
    "Compliance",
    "campaigns",
    "Installation photos",
    "/admin/campaigns?tab=for-review&source=installation",
    (api, limit, offset) =>
      api.GET("/api/v1/admin/installation-evidence/pending", {
        params: { query: { limit, offset } },
      }),
    (r) =>
      task(
        `photos:${r.id}`,
        "campaigns",
        r.submitted_at,
        "Submitted",
        present(r.driver_name),
        `Installation photos for ${present(r.campaign_name)}`,
        `/admin/campaigns/${r.campaign_id}?drawer=job&job=${r.assignment_id}#drivers`,
      ),
  ),
  source(
    "checks",
    "Compliance",
    "trips",
    "In-person checks",
    "/admin/trip-checks?tab=in-person",
    (api, limit, offset) =>
      api.GET("/api/v1/admin/evidence-verifications", {
        params: {
          query: {
            limit,
            offset,
            status: "pending",
            verification_type: "physical_spot_check",
            oldest_first: true,
          },
        },
      }),
    (r) =>
      task(
        `check:${r.id}`,
        "trips",
        r.issued_at,
        "Requested",
        present(r.driver_name),
        "In-person check to record",
        `/admin/trip-checks?tab=in-person&check=${r.id}`,
      ),
  ),
  source(
    "batches",
    "Finance",
    "money",
    "Payment runs",
    "/admin/money?tab=payouts",
    (api, limit, offset) =>
      api.GET("/api/v1/admin/payout-batches/summaries", {
        params: { query: { limit, offset, needs_attention: true, oldest_first: true } },
      }),
    (r) =>
      task(
        `run:${r.id}`,
        "money",
        r.created_at,
        "Created",
        `Payment run ${formatDate(r.created_at)}`,
        [
          r.status === "reserved" && r.approval_mode === "maker_checker" && !r.approved_at
            ? "Needs approval"
            : null,
          (r.outcomes.failed ?? 0) > 0 ? "Has failed payments" : null,
        ]
          .filter(Boolean)
          .join(" · "),
        `/admin/money?tab=payouts&batch=${r.id}`,
      ),
  ),
  source(
    "alerts",
    "Finance",
    "money",
    "Payment problems",
    "/admin/money?tab=payouts#problems",
    (api, limit, offset) =>
      api.GET("/api/v1/admin/payouts/automatic/alerts", {
        params: { query: { limit, offset, alert_status: "open", oldest_first: true } },
      }),
    (r) =>
      task(
        `alert:${r.id}`,
        "money",
        r.created_at,
        "Raised",
        "Automatic payouts",
        r.driver_name ? `Payment problem for ${r.driver_name}` : "Payment problem to review",
        r.batch_id
          ? `/admin/money?tab=payouts&batch=${r.batch_id}`
          : "/admin/money?tab=payouts#problems",
      ),
  ),
  source(
    "corrections",
    "Finance",
    "money",
    "Pay corrections",
    "/admin/money?tab=corrections",
    (api, limit, offset) =>
      api.GET("/api/v1/admin/payouts/correction-orders", {
        params: { query: { limit, offset, status: "pending_approval", oldest_first: true } },
      }),
    (r) =>
      task(
        `correction:${r.id}`,
        "money",
        r.created_at,
        "Created",
        present(r.campaign_name),
        "Pay correction to approve",
        `/admin/money?tab=corrections&correction=${r.id}`,
      ),
  ),
  source(
    "complaints",
    "Customer Service",
    "support",
    "Complaints",
    "/admin/support?tab=complaints",
    (api, limit, offset) =>
      api.GET("/api/v1/admin/complaints", {
        params: { query: { limit, offset, status: "open", oldest_first: true } },
      }),
    (r) =>
      task(
        `complaint:${r.id}`,
        "support",
        r.last_message_at,
        "Last message",
        present(r.party_name),
        `Complaint · ${CATEGORY_LABELS[r.category]}`,
        `/admin/support?tab=complaints&complaint=${r.id}`,
      ),
  ),
  source(
    "contacts",
    "Customer Service",
    "support",
    "Driver contact",
    "/admin/support?tab=contact",
    (api, limit, offset) =>
      api.GET("/api/v1/admin/manual-driver-contact-tasks", {
        params: { query: { limit, offset, history: false, open_only: true, oldest_first: true } },
      }),
    (r) =>
      task(
        `contact:${r.id}`,
        "support",
        r.created_at,
        "Requested",
        present(r.driver_name),
        "Driver contact task",
        `/admin/support?tab=contact&driver_profile_id=${r.driver_profile_id}&task=${r.id}`,
      ),
  ),
  source(
    "disputes",
    "Customer Service",
    "support",
    "Trip disputes",
    "/admin/trip-checks",
    (api, limit, offset) =>
      api.GET("/api/v1/admin/fraud-disputes", {
        params: { query: { limit, offset, status: "open", oldest_first: true } },
      }),
    (r) =>
      task(
        `dispute:${r.id}`,
        "support",
        r.created_at,
        "Submitted",
        present(r.driver_name),
        "Disputes a trip review",
        `/admin/trip-checks?flag=${r.fraud_flag_id}`,
      ),
  ),
  source(
    "changes",
    "Admin",
    "campaigns",
    "Change requests",
    "/admin/campaigns?tab=for-review&source=changes",
    (api, limit, offset) =>
      api.GET("/api/v1/admin/campaign-change-requests/pending", {
        params: { query: { limit, offset, status: "pending_admin" } },
      }),
    (r) =>
      task(
        `change:${r.id}`,
        "campaigns",
        r.created_at,
        "Requested",
        present(r.campaign_name),
        "Change request for review",
        `/admin/campaigns/${r.campaign_id}#overview`,
      ),
  ),
  source(
    "paused",
    "Admin",
    "campaigns",
    "Paused campaigns",
    "/admin/campaigns?tab=live&source=paused",
    (api, limit, offset) =>
      api.GET("/api/v1/admin/campaigns", {
        params: { query: { limit, offset, status: "paused", oldest_first: true } },
      }),
    (r) =>
      task(
        `paused:${r.id}`,
        "campaigns",
        r.updated_at,
        "Updated",
        r.name,
        "Paused campaign",
        `/admin/campaigns/${r.id}#overview`,
      ),
  ),
];
export const readQueueSource = cache(async (id: string, limit: number, offset = 0) =>
  sources.find((s) => s.id === id)?.read(createApiClient(await getSessionToken()), limit, offset),
);
async function previewLimit() {
  return (await headers()).get("x-cardvert-admin-path") === "/admin" ? 5 : 1;
}
export async function collectWorkQueue(api: ApiClient, limit = 5): Promise<QueueCollections> {
  return combine(await Promise.all(sources.map((s) => s.read(api, limit, 0))));
}
function combine(reads: Awaited<ReturnType<Source["read"]>>[]): QueueCollections {
  const empty = (): QueueRows => Object.assign([] as QueueTask[], { total: 0, counts: {} });
  const result: QueueCollections = {
    Operations: empty(),
    Compliance: empty(),
    Finance: empty(),
    "Customer Service": empty(),
    Admin: empty(),
  };
  sources.forEach((source, index) => {
    const rows = result[source.department];
    const read = reads[index];
    if (!read) {
      result[source.department] = undefined;
      return;
    }
    if (!rows) return;
    rows.push(...read.items);
    rows.total! += read.total;
    rows.counts![source.area] = (rows.counts![source.area] ?? 0) + read.total;
  });
  departments.forEach((d) =>
    result[d]?.sort((a, b) => Date.parse(a.at) - Date.parse(b.at) || a.key.localeCompare(b.key)),
  );
  return result;
}
export const readWorkQueue = cache(async () => {
  const limit = await previewLimit();
  return combine(await Promise.all(sources.map((s) => readQueueSource(s.id, limit))));
});
export function waitingCounts(queue: QueueCollections) {
  const count = (area?: Area) => {
    const required: readonly Department[] = area
      ? [...new Set(sources.filter((s) => s.area === area).map((s) => s.department))]
      : departments;
    if (required.some((d) => queue[d] === undefined)) return undefined;
    return required.reduce<number>(
      (n, d) => n + (area ? (queue[d]!.counts?.[area] ?? 0) : (queue[d]!.total ?? 0)),
      0,
    );
  };
  return {
    total: count(),
    drivers: count("drivers"),
    campaigns: count("campaigns"),
    trips: count("trips"),
    money: count("money"),
    support: count("support"),
  };
}
