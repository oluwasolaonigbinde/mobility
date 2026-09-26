import type { Metadata } from "next";
import Link from "next/link";
import { requireRole } from "@/lib/auth/current-user";
import { createApiClient } from "@/lib/api/client";
import { getSessionToken } from "@/lib/auth/session";
import { formatCount } from "@/lib/format";
import { Panel } from "@/components/ui/panel";

export const metadata: Metadata = { title: "Waiting for you" };

type Api = ReturnType<typeof createApiClient>;
type Read = { data?: unknown; error?: unknown };
type Item = { label: string; href: string; read: (api: Api) => Promise<Read> };

const paged = (read: Read) => (read.data as { total?: number } | undefined)?.total;
const listed = (read: Read) => (read.data as { items?: unknown[] } | undefined)?.items?.length;

// D38(e): Terrax departments are sections of one work queue, not separate roles.
const SECTIONS: Array<{
  title: string;
  items: Array<Item & { count: (read: Read) => number | undefined }>;
}> = [
  {
    title: "Operations",
    items: [
      {
        label: "New driver applications",
        href: "/admin/driver-applications",
        count: paged,
        read: (api) =>
          api.GET("/api/v1/admin/driver-applications", { params: { query: { limit: 1 } } }),
      },
      {
        label: "Accepted offers waiting to start",
        href: "/admin/assignments",
        count: paged,
        read: (api) =>
          api.GET("/api/v1/admin/campaign-assignments", {
            params: { query: { limit: 1, status: "accepted" } },
          }),
      },
      {
        label: "Trip reviews",
        href: "/admin/fraud",
        count: paged,
        read: (api) =>
          api.GET("/api/v1/admin/fraud-flags", { params: { query: { limit: 1, status: "open" } } }),
      },
      {
        label: "Late trip data",
        href: "/admin/late-data",
        count: paged,
        read: (api) =>
          api.GET("/api/v1/admin/trips/quarantined-batches", {
            params: { query: { limit: 1, status: "quarantined" } },
          }),
      },
    ],
  },
  {
    title: "Compliance",
    items: [
      {
        label: "Campaigns to review",
        href: "/admin/approvals",
        count: paged,
        read: (api) =>
          api.GET("/api/v1/admin/campaigns/pending-review", { params: { query: { limit: 1 } } }),
      },
      {
        label: "Artwork to review",
        href: "/admin/approvals",
        count: paged,
        read: (api) =>
          api.GET("/api/v1/admin/creatives/pending-review", { params: { query: { limit: 1 } } }),
      },
      {
        label: "Installation photos to review",
        href: "/admin/approvals",
        count: listed,
        read: (api) => api.GET("/api/v1/admin/installation-evidence/pending"),
      },
      {
        label: "Physical checks",
        href: "/admin/fraud",
        count: listed,
        read: (api) =>
          api.GET("/api/v1/admin/evidence-verifications", {
            params: { query: { status: "pending", verification_type: "physical_spot_check" } },
          }),
      },
    ],
  },
  {
    title: "Finance",
    items: [
      {
        label: "Payout batches to approve or send",
        href: "/admin/payouts/batches",
        count: paged,
        read: (api) =>
          api.GET("/api/v1/admin/payout-batches/summaries", {
            params: { query: { limit: 1, batch_status: "reserved" } },
          }),
      },
      {
        label: "Payout batches with failed payments",
        href: "/admin/payouts/batches",
        count: paged,
        read: (api) =>
          api.GET("/api/v1/admin/payout-batches/summaries", {
            params: { query: { limit: 1, batch_status: "failed" } },
          }),
      },
      {
        label: "Pay corrections to approve",
        href: "/admin/payouts/corrections",
        count: paged,
        read: (api) =>
          api.GET("/api/v1/admin/payouts/correction-orders", {
            params: { query: { limit: 1, status: "pending_approval" } },
          }),
      },
    ],
  },
  {
    title: "Customer Service",
    items: [
      {
        label: "Driver contact tasks",
        href: "/admin/contact",
        count: paged,
        read: (api) =>
          api.GET("/api/v1/admin/manual-driver-contact-tasks", { params: { query: { limit: 1 } } }),
      },
      {
        label: "Trip-review disputes to answer",
        href: "/admin/fraud",
        count: paged,
        read: (api) =>
          api.GET("/api/v1/admin/fraud-disputes", {
            params: { query: { limit: 1, status: "open" } },
          }),
      },
    ],
  },
  {
    title: "Admin",
    items: [
      {
        label: "Campaign changes to review",
        href: "/admin/approvals",
        count: listed,
        read: (api) => api.GET("/api/v1/admin/campaign-change-requests/pending"),
      },
      {
        label: "Paused campaigns",
        href: "/admin/billing",
        count: paged,
        read: (api) =>
          api.GET("/api/v1/admin/campaigns", { params: { query: { limit: 1, status: "paused" } } }),
      },
    ],
  },
];

/** A read that errors, returns no data or rejects shows "Couldn't check" for that item only. */
async function countFor(api: Api, item: (typeof SECTIONS)[number]["items"][number]) {
  try {
    const read = await item.read(api);
    return read.error || read.data === undefined ? undefined : item.count(read);
  } catch {
    return undefined;
  }
}

export default async function AdminWorkQueuePage() {
  await requireRole("admin");
  const api = createApiClient(await getSessionToken());
  const counts = await Promise.all(
    SECTIONS.map((section) => Promise.all(section.items.map((item) => countFor(api, item)))),
  );

  return (
    <div className="animate-rise mx-auto max-w-6xl">
      <h1 className="font-display text-3xl font-semibold tracking-tight">Waiting for you</h1>
      <p className="text-muted mt-1 mb-8 text-sm">
        Work for each Terrax Media department. Open an item to deal with it.
      </p>
      <div className="grid gap-4 md:grid-cols-2">
        {SECTIONS.map((section, sectionIndex) => (
          <Panel key={section.title} className="p-5">
            <section aria-labelledby={`queue-${sectionIndex}`}>
              <h2 id={`queue-${sectionIndex}`} className="font-medium">
                {section.title}
              </h2>
              <ul className="divide-edge/60 mt-3 divide-y">
                {section.items.map((item, itemIndex) => {
                  const count = counts[sectionIndex]?.[itemIndex];
                  return (
                    <li key={item.label}>
                      <Link
                        href={item.href}
                        className="hover:text-amber flex items-center justify-between gap-3 py-2.5 text-sm"
                      >
                        <span>{item.label}</span>
                        <span
                          className={
                            count === undefined
                              ? "text-coral text-xs"
                              : count > 0
                                ? "text-amber font-semibold"
                                : "text-faint text-xs"
                          }
                        >
                          {count === undefined
                            ? "Couldn't check"
                            : count > 0
                              ? formatCount(count)
                              : "Nothing waiting"}
                        </span>
                      </Link>
                    </li>
                  );
                })}
              </ul>
            </section>
          </Panel>
        ))}
      </div>
    </div>
  );
}
