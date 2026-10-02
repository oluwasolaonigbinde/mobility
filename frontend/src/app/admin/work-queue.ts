import { cache } from "react";
import { createApiClient, type ApiClient } from "@/lib/api/client";
import { getSessionToken } from "@/lib/auth/session";
import { completePages } from "./worklist-reads";
import { readTripContext } from "./trip-checks/reads";
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
export type QueueTask = {
  key: string;
  area: "drivers" | "campaigns" | "trips" | "money" | "support";
  at: string;
  event: string;
  describe: () => Promise<{ name: string; reason: string; href: string }>;
};
export type QueueCollections = Record<Department, QueueTask[] | undefined>;

function present(value: string | null | undefined): string {
  if (!value?.trim()) throw new Error("Incomplete queue context");
  return value;
}
function task(
  key: string,
  area: QueueTask["area"],
  at: string | null | undefined,
  event: string,
  describe: QueueTask["describe"],
): QueueTask {
  if (!at || !Number.isFinite(Date.parse(at))) throw new Error("Incomplete queue date");
  return { key, area, at, event, describe };
}
async function unpaged<T extends { id: string }>(
  response: Promise<{ data?: { items: T[] } }>,
): Promise<T[]> {
  const { data } = await response;
  if (
    !data ||
    !Array.isArray(data.items) ||
    new Set(data.items.map((item) => item.id)).size !== data.items.length
  )
    throw new Error("Incomplete queue");
  return data.items;
}

export async function collectWorkQueue(api: ApiClient): Promise<QueueCollections> {
  const memo = new Map<string, Promise<string>>();
  function name(kind: "driver" | "campaign", id: string) {
    const key = `${kind}:${id}`;
    if (!memo.has(key))
      memo.set(
        key,
        (async () => {
          if (kind === "driver") {
            const { data } = await api.GET("/api/v1/admin/drivers/{driver_profile_id}", {
              params: { path: { driver_profile_id: id } },
            });
            if (!data || data.id !== id) throw new Error("Invalid driver identity");
            return present(data.full_name);
          }
          const { data } = await api.GET("/api/v1/admin/campaigns/{campaign_id}", {
            params: { path: { campaign_id: id } },
          });
          if (!data || data.id !== id) throw new Error("Invalid campaign identity");
          return present(data.name);
        })(),
      );
    return memo.get(key)!;
  }
  const campaignLink = (id: string, section: string) => `/admin/campaigns/${id}#${section}`;
  const sources: { department: Department; read: () => Promise<QueueTask[]> }[] = [
    {
      department: "Operations",
      read: async () =>
        (
          await completePages((offset) =>
            api.GET("/api/v1/admin/driver-applications", {
              params: { query: { limit: 100, offset } },
            }),
          )
        ).map((row) =>
          task(`application:${row.id}`, "drivers", row.created_at, "Created", async () => ({
            name: present(row.full_name),
            reason: "New application",
            href: row.driver_profile_id
              ? `/admin/drivers/${row.driver_profile_id}#checklist`
              : `/admin/drivers/applicant/${row.id}#checklist`,
          })),
        ),
    },
    {
      department: "Operations",
      read: async () =>
        (
          await completePages((offset) =>
            api.GET("/api/v1/admin/vehicles", {
              params: { query: { limit: 100, offset, status: "pending" } },
            }),
          )
        ).map((row) =>
          task(`vehicle:${row.id}`, "drivers", row.created_at, "Created", async () => ({
            name: `${present(row.driver_profile.full_name)} · ${present(row.plate_number)}`,
            reason: "Car to approve",
            href: `/admin/drivers/${row.driver_profile_id}#cars`,
          })),
        ),
    },
    {
      department: "Operations",
      read: async () =>
        (
          await completePages((offset) =>
            api.GET("/api/v1/admin/campaign-assignments", {
              params: { query: { limit: 100, offset, status: "accepted" } },
            }),
          )
        ).map((row) =>
          task(`job:${row.id}`, "campaigns", row.accepted_at, "Accepted", async () => ({
            name: `${present(row.driver_profile?.full_name)} · ${present(row.vehicle?.plate_number)}`,
            reason: `Accepted job waiting to start on ${present(row.campaign?.name)}`,
            href: `/admin/campaigns/${row.campaign_id}?drawer=job&job=${row.id}#drivers`,
          })),
        ),
    },
    ...(["open", "acknowledged"] as const).map((status) => ({
      department: "Operations" as const,
      read: async () =>
        (
          await completePages((offset) =>
            api.GET("/api/v1/admin/fraud-flags", {
              params: { query: { limit: 100, offset, status } },
            }),
          )
        ).map((row) =>
          task(`flag:${row.id}`, "trips", row.detected_at, "Detected", async () => ({
            name: await name("driver", row.driver_profile_id),
            reason: `Suspicious trip · ${row.money_effect.held_currency ? `pay held ${formatMoneyExact(row.money_effect.held_pending_net, row.money_effect.held_currency)}` : "no pay held"}`,
            href: `/admin/trip-checks?tab=suspicious&flag=${row.id}`,
          })),
        ),
    })),
    {
      department: "Operations",
      read: async () =>
        (
          await completePages((offset) =>
            api.GET("/api/v1/admin/trips/quarantined-batches", {
              params: { query: { limit: 100, offset, status: "quarantined" } },
            }),
          )
        ).map((row) =>
          task(`late:${row.id}`, "trips", row.received_at, "Received", async () => {
            const trip = await readTripContext(api, row.trip_session_id);
            return {
              name: `${trip.name} · ${trip.plate}`,
              reason: `Late upload for ${formatDate(trip.date)} trip`,
              href: `/admin/trip-checks?tab=late&late=${row.id}`,
            };
          }),
        ),
    },
    {
      department: "Compliance",
      read: async () =>
        (
          await completePages((offset) =>
            api.GET("/api/v1/admin/campaigns/pending-review", {
              params: { query: { limit: 100, offset } },
            }),
          )
        ).map((row) =>
          task(`campaign:${row.id}`, "campaigns", row.created_at, "Created", async () => ({
            name: present(row.name),
            reason: "Campaign for review",
            href: campaignLink(row.id, "overview"),
          })),
        ),
    },
    {
      department: "Compliance",
      read: async () =>
        (
          await completePages(async (offset) => {
            const response = await api.GET("/api/v1/admin/creatives/pending-review", {
              params: { query: { limit: 100, offset } },
            });
            return {
              data: response.data
                ? {
                    ...response.data,
                    items: response.data.items.map((row) => ({ ...row, id: row.creative.id })),
                  }
                : undefined,
            };
          })
        ).map((row) =>
          task(`artwork:${row.id}`, "campaigns", row.creative.created_at, "Created", async () => ({
            name: present(row.campaign_name),
            reason: `Artwork for review · ${present(row.creative.name)}`,
            href: campaignLink(row.creative.campaign_id, "artwork"),
          })),
        ),
    },
    {
      department: "Compliance",
      read: async () =>
        (await unpaged(api.GET("/api/v1/admin/installation-evidence/pending"))).map((row) =>
          task(`photos:${row.id}`, "campaigns", row.submitted_at, "Submitted", async () => ({
            name: await name("driver", row.driver_profile_id),
            reason: `Installation photos for ${await name("campaign", row.campaign_id)}`,
            href: `/admin/campaigns/${row.campaign_id}?drawer=job&job=${row.assignment_id}#drivers`,
          })),
        ),
    },
    {
      department: "Compliance",
      read: async () =>
        (
          await completePages((offset) =>
            api.GET("/api/v1/admin/evidence-verifications", {
              params: {
                query: {
                  limit: 100,
                  offset,
                  status: "pending",
                  verification_type: "physical_spot_check",
                },
              },
            }),
          )
        ).map((row) =>
          task(`check:${row.id}`, "trips", row.issued_at, "Requested", async () => ({
            name: await name("driver", row.driver_profile_id),
            reason: "In-person check to record",
            href: `/admin/trip-checks?tab=in-person&check=${row.id}`,
          })),
        ),
    },
    {
      department: "Finance",
      read: async () =>
        (
          await completePages((offset) =>
            api.GET("/api/v1/admin/payout-batches/summaries", {
              params: { query: { limit: 100, offset } },
            }),
          )
        )
          .filter(
            (row) =>
              (row.status === "reserved" &&
                row.approval_mode === "maker_checker" &&
                !row.approved_at) ||
              (row.outcomes.failed ?? 0) > 0,
          )
          .map((row) =>
            task(`run:${row.id}`, "money", row.created_at, "Created", async () => ({
              name: `Payment run ${formatDate(row.created_at)}`,
              reason: [
                row.status === "reserved" &&
                row.approval_mode === "maker_checker" &&
                !row.approved_at
                  ? "Needs approval"
                  : null,
                (row.outcomes.failed ?? 0) > 0 ? "Has failed payments" : null,
              ]
                .filter(Boolean)
                .join(" · "),
              href: `/admin/money?tab=payouts&batch=${row.id}`,
            })),
          ),
    },
    {
      department: "Finance",
      read: async () =>
        (
          await completePages((offset) =>
            api.GET("/api/v1/admin/payouts/automatic/alerts", {
              params: { query: { limit: 100, offset, alert_status: "open" } },
            }),
          )
        ).map((row) =>
          task(`alert:${row.id}`, "money", row.created_at, "Raised", async () => ({
            name: "Automatic payouts",
            reason: row.driver_name
              ? `Payment problem for ${row.driver_name}`
              : "Payment problem to review",
            href: row.batch_id
              ? `/admin/money?tab=payouts&batch=${row.batch_id}`
              : "/admin/money?tab=payouts#problems",
          })),
        ),
    },
    {
      department: "Finance",
      read: async () =>
        (
          await completePages((offset) =>
            api.GET("/api/v1/admin/payouts/correction-orders", {
              params: { query: { limit: 100, offset, status: "pending_approval" } },
            }),
          )
        ).map((row) =>
          task(`correction:${row.id}`, "money", row.created_at, "Created", async () => ({
            name: await name("campaign", row.campaign_id),
            reason: "Pay correction to approve",
            href: `/admin/money?tab=corrections&correction=${row.id}`,
          })),
        ),
    },
    {
      department: "Customer Service",
      read: async () =>
        (
          await completePages((offset) =>
            api.GET("/api/v1/admin/complaints", {
              params: { query: { limit: 100, offset, status: "open" } },
            }),
          )
        ).map((row) =>
          task(`complaint:${row.id}`, "support", row.last_message_at, "Last message", async () => ({
            name: present(row.party_name),
            reason: `Complaint · ${CATEGORY_LABELS[row.category]}`,
            href: `/admin/support?tab=complaints&complaint=${row.id}`,
          })),
        ),
    },
    {
      department: "Customer Service",
      read: async () =>
        (
          await completePages((offset) =>
            api.GET("/api/v1/admin/manual-driver-contact-tasks", {
              params: { query: { limit: 100, offset, history: false } },
            }),
          )
        )
          .filter((row) => !row.completed_at && row.status === "open")
          .map((row) =>
            task(`contact:${row.id}`, "support", row.created_at, "Requested", async () => ({
              name: present(row.driver_name),
              reason: "Driver contact task",
              href: `/admin/support?tab=contact&driver_profile_id=${row.driver_profile_id}&task=${row.id}`,
            })),
          ),
    },
    {
      department: "Customer Service",
      read: async () =>
        (
          await completePages((offset) =>
            api.GET("/api/v1/admin/fraud-disputes", {
              params: { query: { limit: 100, offset, status: "open" } },
            }),
          )
        ).map((row) =>
          task(`dispute:${row.id}`, "support", row.created_at, "Submitted", async () => ({
            name: await name("driver", row.driver_profile_id),
            reason: "Disputes a trip review",
            href: `/admin/trip-checks?tab=suspicious&flag=${row.fraud_flag_id}`,
          })),
        ),
    },
    {
      department: "Admin",
      read: async () =>
        (await unpaged(api.GET("/api/v1/admin/campaign-change-requests/pending")))
          .filter((row) => row.status === "pending_admin")
          .map((row) =>
            task(`change:${row.id}`, "campaigns", row.created_at, "Requested", async () => ({
              name: await name("campaign", row.campaign_id),
              reason: "Change request for review",
              href: campaignLink(row.campaign_id, "overview"),
            })),
          ),
    },
    {
      department: "Admin",
      read: async () =>
        (
          await completePages((offset) =>
            api.GET("/api/v1/admin/campaigns", {
              params: { query: { limit: 100, offset, status: "paused" } },
            }),
          )
        ).map((row) =>
          task(`paused:${row.id}`, "campaigns", row.updated_at, "Updated", async () => ({
            name: present(row.name),
            reason: "Paused campaign",
            href: campaignLink(row.id, "overview"),
          })),
        ),
    },
  ];
  const result: QueueCollections = {
    Operations: [],
    Compliance: [],
    Finance: [],
    "Customer Service": [],
    Admin: [],
  };
  for (let index = 0; index < sources.length; index += 4)
    await Promise.all(
      sources.slice(index, index + 4).map(async (source) => {
        try {
          const rows = await source.read();
          if (result[source.department]) result[source.department]!.push(...rows);
        } catch {
          result[source.department] = undefined;
        }
      }),
    );
  for (const department of departments)
    result[department]?.sort(
      (a, b) => Date.parse(a.at) - Date.parse(b.at) || a.key.localeCompare(b.key),
    );
  return result;
}

export const readWorkQueue = cache(async () =>
  collectWorkQueue(createApiClient(await getSessionToken())),
);
export function waitingCounts(queue: QueueCollections) {
  const area = (value: QueueTask["area"]) => {
    const required: Department[] =
      value === "drivers"
        ? ["Operations"]
        : value === "campaigns"
          ? ["Operations", "Compliance", "Admin"]
          : value === "trips"
            ? ["Operations", "Compliance"]
            : value === "money"
              ? ["Finance"]
              : ["Customer Service"];
    if (required.some((department) => queue[department] === undefined)) return undefined;
    return departments.reduce(
      (total, department) =>
        total + (queue[department]?.filter((row) => row.area === value).length ?? 0),
      0,
    );
  };
  return {
    total: departments.every((department) => queue[department] !== undefined)
      ? departments.reduce((total, department) => total + queue[department]!.length, 0)
      : undefined,
    drivers: area("drivers"),
    campaigns: area("campaigns"),
    trips: area("trips"),
    money: area("money"),
    support: area("support"),
  };
}
