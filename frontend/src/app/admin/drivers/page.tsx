import type { Metadata } from "next";
import Link from "next/link";
import { createApiClient } from "@/lib/api/client";
import { getSessionToken } from "@/lib/auth/session";
import { adminStatus } from "@/lib/status/admin";
import { PageHeader } from "@/components/ui/page-header";
import { Pagination } from "@/components/ui/pagination";
import { QueueSearch, QueueUnavailable } from "../queue-search";
export const metadata: Metadata = { title: "Drivers" };
const tabs = [
  { id: "applicants", title: "Applicants", status: "pending" },
  { id: "active", title: "Active", status: "active" },
  { id: "suspended", title: "Suspended", status: "suspended" },
  { id: "not-approved", title: "Not approved", status: "rejected" },
] as const;
export default async function DriversPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | undefined>>;
}) {
  const p = await searchParams;
  const tab = tabs.find((t) => t.id === p.tab) ?? tabs[0];
  const cars = p.source === "cars";
  const applicants = tab.id === "applicants" && !cars;
  const offset = Number.isFinite(Number(p.offset)) ? Math.max(0, Math.floor(Number(p.offset))) : 0;
  const api = createApiClient(await getSessionToken());
  const query = { q: p.q, limit: 25, offset };
  type Row = {
    key: string;
    name: string;
    phone?: string | null;
    city?: string | null;
    plate?: string | null;
    status: string;
    next?: string;
    href: string;
  };
  let rows: Row[] | undefined;
  let total: number | undefined;
  try {
    if (applicants) {
      const { data } = await api.GET("/api/v1/admin/driver-applications", {
        params: { query: { ...query, include_staff_added: true } },
      });
      rows = data?.applicants?.map((a) => ({
        key: a.kind + ":" + a.id,
        name: a.full_name,
        phone: a.phone,
        city: a.service_city,
        status: a.kind === "staff_added" ? "Added by staff" : "Application for review",
        href: a.driver_profile_id
          ? `/admin/drivers/${a.driver_profile_id}${a.application_id ? `?application=${a.application_id}` : ""}`
          : `/admin/drivers/applicant/${a.application_id}`,
      }));
      total = data?.total;
    } else if (cars) {
      const { data } = await api.GET("/api/v1/admin/vehicles", { params: { query } });
      rows = data?.items.map((v) => ({
        key: v.id,
        name: v.driver_profile.full_name,
        phone: v.driver_profile.phone,
        plate: v.plate_number,
        status: adminStatus(v.status),
        next: v.status === "pending" ? "Review car documents" : undefined,
        href: `/admin/drivers/${v.driver_profile_id}#cars`,
      }));
      total = data?.total;
    } else {
      const { data } = await api.GET("/api/v1/admin/drivers", {
        params: { query: { ...query, onboarding_status: tab.status } },
      });
      rows = data?.items.map((d) => ({
        key: d.id,
        name: d.full_name,
        phone: d.phone,
        city: d.service_city,
        status: adminStatus(d.onboarding_status, "driver"),
        next: d.onboarding_status === "suspended" ? "Review suspension" : undefined,
        href: `/admin/drivers/${d.id}`,
      }));
      total = data?.total;
    }
  } catch {
    rows = undefined;
  }
  return (
    <div className="mx-auto max-w-6xl">
      <PageHeader
        title="Drivers"
        actions={
          <Link href="/admin/drivers/new" className="text-cyan underline">
            Add driver
          </Link>
        }
      />
      <nav aria-label="Driver status" className="mb-5 flex gap-2 overflow-x-auto">
        {tabs.map((t) => (
          <Link
            key={t.id}
            href={`/admin/drivers?tab=${t.id}`}
            aria-current={t.id === tab.id ? "page" : undefined}
            className="rounded-lg px-4 py-2 text-sm whitespace-nowrap"
          >
            {t.title}
          </Link>
        ))}
      </nav>
      <QueueSearch q={p.q} label={cars ? "Search driver names or car plates" : "Search drivers"}>
        <input type="hidden" name="tab" value={tab.id} />
        {cars ? <input type="hidden" name="source" value="cars" /> : null}
      </QueueSearch>
      {!rows || total === undefined ? (
        <QueueUnavailable />
      ) : (
        <>
          <p className="text-muted mb-3 text-sm">
            {total} matching {cars ? "cars" : applicants ? "applicants" : "drivers"}
          </p>
          {!rows.length ? (
            <p>
              {total > 0
                ? `No ${cars ? "cars" : applicants ? "applicants" : "drivers"} on this page.`
                : p.q
                  ? "No matching drivers."
                  : applicants
                    ? "No applicants waiting."
                    : "No drivers recorded."}
            </p>
          ) : (
            <div className="grid gap-3">
              {rows.map((r) => (
                <Link
                  key={r.key}
                  href={r.href}
                  className="border-edge hover:bg-raised grid gap-2 rounded-xl border p-4 text-sm md:grid-cols-[2fr_1fr_1fr_1.5fr]"
                >
                  <div>
                    <h2 className="font-medium">{r.name}</h2>
                    <p className="text-muted">{r.phone ?? "No phone recorded"}</p>
                  </div>
                  <p>{r.city}</p>
                  <p>{r.plate}</p>
                  <div>
                    <p>{r.status}</p>
                    {r.next ? <p className="text-muted">Next: {r.next}</p> : null}
                  </div>
                </Link>
              ))}
            </div>
          )}
          <Pagination
            total={total}
            limit={25}
            offset={offset}
            hrefFor={(n) =>
              "/admin/drivers?" +
              new URLSearchParams({
                tab: tab.id,
                q: p.q ?? "",
                offset: String(n),
                ...(cars ? { source: "cars" } : {}),
              })
            }
          />
        </>
      )}
    </div>
  );
}
