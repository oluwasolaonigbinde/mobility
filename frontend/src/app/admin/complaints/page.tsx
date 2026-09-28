import type { Metadata } from "next";
import Link from "next/link";
import { createApiClient } from "@/lib/api/client";
import { getSessionToken } from "@/lib/auth/session";
import { PageHeader } from "@/components/ui/page-header";
import { Pagination } from "@/components/ui/pagination";
import { Panel } from "@/components/ui/panel";
import { StatusChip } from "@/components/ui/status-chip";
import { EmptyState } from "@/components/ui/empty-state";
import { CATEGORY_LABELS, STAFF_STATUS, formatWat } from "@/lib/complaints/labels";
import { readComplaintApi } from "@/lib/complaints/read";

export const metadata: Metadata = { title: "Customer Service" };

const LIMIT = 25;
const VIEWS = [
  { status: "open", label: "Needs a reply" },
  { status: "answered", label: "Waiting on them" },
  { status: "resolved", label: "Resolved" },
  { status: "", label: "All" },
] as const;

type Status = "open" | "answered" | "resolved";

export default async function CustomerServiceInbox({
  searchParams,
}: {
  searchParams: Promise<{ status?: string; mine?: string; offset?: string }>;
}) {
  const p = await searchParams;
  // No filter in the URL means the default "Needs a reply" view; an empty value means All.
  const status: Status | undefined =
    p.status === undefined
      ? "open"
      : (["open", "answered", "resolved"] as const).find((value) => value === p.status);
  const mine = p.mine === "true";
  const offset = Math.max(0, Math.floor(Number(p.offset) || 0));
  const hrefFor = (next: { status?: string; mine?: boolean; offset?: number }) => {
    const query = new URLSearchParams({
      status: next.status ?? status ?? "",
      mine: String(next.mine ?? mine),
      offset: String(next.offset ?? 0),
    });
    return `/admin/complaints?${query.toString()}`;
  };

  const api = createApiClient(await getSessionToken());
  const list = await readComplaintApi(() =>
    api.GET("/api/v1/admin/complaints", {
      params: {
        query: { limit: LIMIT, offset, assigned_to_me: mine, ...(status ? { status } : {}) },
      },
    }),
  );

  return (
    <div className="animate-rise mx-auto max-w-5xl">
      <PageHeader title="Customer Service" eyebrow="Complaints from drivers and advertisers" />
      <nav aria-label="Complaint views" className="mb-5 flex flex-wrap items-center gap-2 text-sm">
        {VIEWS.map((view) => {
          const active = (status ?? "") === view.status;
          return (
            <Link
              key={view.label}
              href={hrefFor({ status: view.status })}
              aria-current={active ? "page" : undefined}
              className={`rounded-full border px-3 py-1 ${active ? "border-amber text-amber" : "border-edge text-muted"}`}
            >
              {view.label}
            </Link>
          );
        })}
        <Link href={hrefFor({ mine: !mine })} className="text-amber ml-2 text-xs">
          {mine ? "Show everyone's" : "Only assigned to me"}
        </Link>
      </nav>

      {list.state !== "ready" ? (
        <Panel className="p-5" role="alert">
          <h2 className="text-base font-semibold">Complaints couldn&apos;t be loaded</h2>
          <p className="text-muted mt-1 text-sm">
            Cardvert couldn&apos;t load the inbox right now.{" "}
            <Link href={hrefFor({ offset })} className="text-amber hover:underline">
              Try again
            </Link>
          </p>
        </Panel>
      ) : list.data.items.length === 0 ? (
        <EmptyState
          title="Nothing here"
          body={
            status === "open"
              ? "No complaint is waiting for a reply."
              : "No complaints match this view."
          }
        />
      ) : (
        <Panel className="overflow-hidden">
          <ul className="divide-edge/60 divide-y">
            {list.data.items.map((item) => {
              const chip = STAFF_STATUS[item.status];
              return (
                <li key={item.id}>
                  <Link
                    href={`/admin/complaints/${item.id}`}
                    className="hover:bg-raised/60 flex flex-wrap items-center justify-between gap-3 px-5 py-3.5"
                  >
                    <span>
                      <span className="block text-sm font-medium">
                        {item.party_name}{" "}
                        <span className="text-muted font-normal">
                          ({item.party === "driver" ? "driver" : "advertiser"})
                        </span>
                      </span>
                      <span className="text-muted block text-xs">
                        {CATEGORY_LABELS[item.category]}
                        {item.reference_label ? ` · ${item.reference_label}` : ""} · Last message{" "}
                        {formatWat(item.last_message_at)} ·{" "}
                        {item.assigned_to_name
                          ? `Assigned to ${item.assigned_to_name}`
                          : "Unassigned"}
                      </span>
                    </span>
                    <StatusChip tone={chip.tone}>{chip.label}</StatusChip>
                  </Link>
                </li>
              );
            })}
          </ul>
        </Panel>
      )}
      {list.state === "ready" ? (
        <Pagination
          total={list.data.total}
          limit={LIMIT}
          offset={offset}
          hrefFor={(next) => hrefFor({ offset: next })}
        />
      ) : null}
    </div>
  );
}
